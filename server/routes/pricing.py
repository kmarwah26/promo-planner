"""Read-side routes for the Promo 1YP wholesale pricing workspace.

Sources the calendarized price grid from Unity Catalog (via the SQL warehouse):
filter options, the 52-week column axis, a windowed page of grid lines with their
per-week promo overrides, the always-on budget roll-up, and the downstream
"finally approved" pricing API.

The grid grain is one line = (plan_year, wholesaler_id, brand_code, prc_code); the
52 ISO weeks are the columns. Per-week promo overrides live in fact_promo_week
(sparse). For the 2027 Plan Builder, in-progress sandbox edits from Lakebase are
overlaid on top of the committed/production data at read time.
"""
from fastapi import APIRouter, Request, Query
from server.routes.sql_exec import run_query, FQ, PROMO_CATALOG, PROMO_SCHEMA, DEFAULT_WAREHOUSE_ID

router = APIRouter(tags=["pricing"])


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return v


def _esc(s: str) -> str:
    """Escape single quotes for safe inlining into SQL string literals."""
    return s.replace("'", "''")


def _promo_table(plan_year: int) -> str:
    """Single source of truth for per-week promo rows across all plan years.

    Both plan years read and write the same governed table, so a Final Submission
    (approval) is immediately visible everywhere in the app.
    """
    return "fact_promo_week"


@router.get("/pricing/filters")
async def get_filters(request: Request):
    """Distinct values for the three filter dropdowns: wholesaler, brand, PRC group."""
    wholesalers = await run_query(request, f"""
        SELECT wholesaler_id, wholesaler_name FROM {FQ}.dim_wholesaler
        ORDER BY wholesaler_id LIMIT 2000
    """)
    brands = await run_query(request, f"""
        SELECT brand_code, brand_name FROM {FQ}.dim_brand ORDER BY brand_name
    """)
    prc = await run_query(request, f"""
        SELECT prc_code, prc_group_name FROM {FQ}.dim_prc_group ORDER BY prc_group_name
    """)
    return {
        "wholesalers": [{"id": w["wholesaler_id"], "name": w["wholesaler_name"]} for w in wholesalers],
        "brands": [{"code": b["brand_code"], "name": b["brand_name"]} for b in brands],
        "prc_groups": [{"code": p["prc_code"], "name": p["prc_group_name"]} for p in prc],
    }


@router.get("/pricing/weeks")
async def weeks(request: Request):
    """The 52 ISO weeks that form the grid's column axis."""
    rows = await run_query(request, f"""
        SELECT week_number, iso_label, week_start_date, week_end_date, date_range_label
        FROM {FQ}.dim_iso_week ORDER BY week_number
    """)
    for r in rows:
        r["week_number"] = _num(r["week_number"])
    return {"weeks": rows}


def _line_where(plan_year, wholesaler, brand, prc, alias=""):
    p = f"{alias}." if alias else ""
    clauses = [f"{p}plan_year = {int(plan_year)}"]
    if wholesaler:
        # wholesaler may be a comma-separated list (multi-select) → IN (...).
        ids = [w.strip() for w in str(wholesaler).split(",") if w.strip()]
        if len(ids) == 1:
            clauses.append(f"{p}wholesaler_id = '{_esc(ids[0])}'")
        elif ids:
            in_list = ",".join(f"'{_esc(w)}'" for w in ids)
            clauses.append(f"{p}wholesaler_id IN ({in_list})")
    if brand:
        clauses.append(f"{p}brand_code = '{_esc(brand)}'")
    if prc:
        clauses.append(f"{p}prc_code = '{_esc(prc)}'")
    return " AND ".join(clauses)


@router.get("/pricing/grid")
async def grid(
    request: Request,
    plan_year: int = 2027,
    wholesaler: str | None = None,
    brand: str | None = None,
    prc_group: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    sandbox_id: str | None = None,
):
    """A windowed page of grid lines with their per-week promo cells.

    Lines are ordered by (wholesaler_id, brand_code, prc_code) and paged with
    LIMIT/OFFSET, so only the visible window is scanned. Per-week overrides for
    the page are left-joined from fact_promo_week; sandbox edits (2027 Plan
    Builder) are overlaid on top so users see their in-progress state.
    """
    where = _line_where(plan_year, wholesaler, brand, prc_group, alias="l")
    # One row per (line, promo week); lines with no promo still appear once (null week).
    rows = await run_query(request, f"""
        WITH page AS (
          SELECT plan_year, wholesaler_id, wholesaler_name, region, state,
                 brand_code, brand_name, prc_code, prc_group_name,
                 qd_min, qd_max, deal_description, base_pptr, curr_max_discount
          FROM {FQ}.fact_price_plan l
          WHERE {where}
          ORDER BY wholesaler_id, brand_code, prc_code
          LIMIT {int(limit)} OFFSET {int(offset)}
        )
        SELECT p.*, pw.week_number, pw.incremental_discount, pw.absolute_discount,
               pw.rec_pptr, pw.approval_status
        FROM page p
        LEFT JOIN {FQ}.{_promo_table(plan_year)} pw
          ON pw.plan_year = p.plan_year AND pw.wholesaler_id = p.wholesaler_id
         AND pw.brand_code = p.brand_code AND pw.prc_code = p.prc_code
        ORDER BY p.wholesaler_id, p.brand_code, p.prc_code, pw.week_number
    """)

    # Group the flat (line, week) rows into one object per line, with a weeks map.
    lines: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        key = f"{r['wholesaler_id']}|{r['brand_code']}|{r['prc_code']}"
        line = lines.get(key)
        if line is None:
            line = {
                "line_key": key,
                "plan_year": _num(r["plan_year"]),
                "wholesaler_id": r["wholesaler_id"],
                "wholesaler_name": r["wholesaler_name"],
                "region": r["region"], "state": r["state"],
                "brand_code": r["brand_code"], "brand_name": r["brand_name"],
                "prc_code": r["prc_code"], "prc_group_name": r["prc_group_name"],
                "qd_min": _num(r["qd_min"]), "qd_max": _num(r["qd_max"]),
                "deal_description": r["deal_description"],
                "base_pptr": _num(r["base_pptr"]),
                "curr_max_discount": _num(r["curr_max_discount"]),
                "reviewed": False,
                "cells": {},   # week_number(str) -> cell
            }
            lines[key] = line
            order.append(key)
        if r["week_number"] is not None:
            wk = int(_num(r["week_number"]))
            line["cells"][str(wk)] = {
                "week": wk,
                "incremental_discount": _num(r["incremental_discount"]),
                "absolute_discount": _num(r["absolute_discount"]),
                "rec_pptr": _num(r["rec_pptr"]),
                "approval_status": r["approval_status"],
                "source": "production",
            }

    # Overlay Lakebase sandbox edits (in-progress, unsubmitted) onto matching cells,
    # and the per-line reviewed flag.
    if sandbox_id:
        from server.routes.planning import get_sandbox_edits, get_reviewed_keys
        reviewed = await get_reviewed_keys(sandbox_id, plan_year)
        for k in reviewed:
            if k in lines:
                lines[k]["reviewed"] = True
        edits = await get_sandbox_edits(sandbox_id, plan_year)
        for e in edits:
            key = f"{e['wholesaler_id']}|{e['brand_code']}|{e['prc_code']}"
            line = lines.get(key)
            if line is None:
                continue  # edit is outside this page
            base = line["base_pptr"]
            inc = e.get("incremental_discount")
            absd = e.get("absolute_discount")
            # Both incremental and absolute discounts are dollars off per case.
            off = absd if absd is not None else (inc if inc is not None else 0)
            rec = base - off
            # The edit's lifecycle status (draft/pending/approved) lives in Lakebase.
            line["cells"][str(e["week_number"])] = {
                "week": e["week_number"],
                "incremental_discount": inc,
                "absolute_discount": absd,
                "rec_pptr": round(rec, 2),
                "approval_status": e.get("status") or "draft",
                "source": "sandbox",
            }

    return {"lines": [lines[k] for k in order], "limit": limit, "offset": offset,
            "count": len(order)}


@router.get("/pricing/budget")
async def budget(
    request: Request,
    plan_year: int = 2027,
    wholesaler: str | None = None,
    brand: str | None = None,
    prc_group: str | None = None,
    sandbox_id: str | None = None,
):
    """Portfolio budget roll-up over the filtered set, for the always-on budget bar.

    Total discount $ = sum(base_pptr - rec_pptr) over promo weeks; plus line count,
    promo-week count, and lines-on-promo. Production numbers come from one cheap UC
    aggregate; when a sandbox is supplied, its in-progress edits are folded in so the
    budget moves live as cells are modified (a sandbox edit replaces production for the
    same line+week; a new week adds one)."""
    lwhere = _line_where(plan_year, wholesaler, brand, prc_group, alias="l")
    agg = await run_query(request, f"""
        WITH lines AS (
          SELECT plan_year, wholesaler_id, brand_code, prc_code, base_pptr
          FROM {FQ}.fact_price_plan l WHERE {lwhere}
        )
        SELECT
          (SELECT count(*) FROM lines) AS n_lines,
          count(pw.week_number) AS n_promo_weeks,
          count(DISTINCT concat(pw.wholesaler_id, pw.brand_code, pw.prc_code)) AS n_lines_on_promo,
          round(sum(l.base_pptr - pw.rec_pptr), 2) AS total_discount,
          round(avg(pw.incremental_discount), 4) AS avg_incremental_discount
        FROM lines l
        JOIN {FQ}.{_promo_table(plan_year)} pw
          ON pw.plan_year = {int(plan_year)} AND pw.wholesaler_id = l.wholesaler_id
         AND pw.brand_code = l.brand_code AND pw.prc_code = l.prc_code
    """)
    r = agg[0] if agg else {}
    out = {
        "n_lines": _num(r.get("n_lines")) or 0,
        "n_promo_weeks": _num(r.get("n_promo_weeks")) or 0,
        "n_lines_on_promo": _num(r.get("n_lines_on_promo")) or 0,
        "total_discount": _num(r.get("total_discount")) or 0.0,
        "avg_incremental_discount": _num(r.get("avg_incremental_discount")) or 0.0,
    }
    if not sandbox_id:
        return out

    # Fold in sandbox edits (respecting the same filters).
    from server.routes.planning import get_sandbox_edits
    edits = await get_sandbox_edits(sandbox_id, plan_year)
    ws_set = {w.strip() for w in str(wholesaler).split(",") if w.strip()} if wholesaler else None
    edits = [e for e in edits
             if (not ws_set or e["wholesaler_id"] in ws_set)
             and (not brand or e["brand_code"] == brand)
             and (not prc_group or e["prc_code"] == prc_group)]
    if not edits:
        return out

    # For each edited cell, look up the line's base_pptr, any existing production
    # rec_pptr (to know if we're replacing a week), and the line's total production
    # promo-week count (to know if the line was already "on promo").
    vals = ",".join(
        f"('{_esc(e['wholesaler_id'])}','{_esc(e['brand_code'])}','{_esc(e['prc_code'])}',{int(e['week_number'])})"
        for e in edits
    )
    rows = await run_query(request, f"""
        WITH s AS (
          SELECT * FROM (VALUES {vals}) AS s(wholesaler_id, brand_code, prc_code, week_number)
        )
        SELECT s.wholesaler_id, s.brand_code, s.prc_code, s.week_number,
               p.base_pptr, pw.rec_pptr AS old_rec,
               (SELECT count(*) FROM {FQ}.{_promo_table(plan_year)} x
                 WHERE x.plan_year = {int(plan_year)} AND x.wholesaler_id = s.wholesaler_id
                   AND x.brand_code = s.brand_code AND x.prc_code = s.prc_code) AS line_prod_weeks
        FROM s
        JOIN {FQ}.fact_price_plan p
          ON p.plan_year = {int(plan_year)} AND p.wholesaler_id = s.wholesaler_id
         AND p.brand_code = s.brand_code AND p.prc_code = s.prc_code
        LEFT JOIN {FQ}.{_promo_table(plan_year)} pw
          ON pw.plan_year = {int(plan_year)} AND pw.wholesaler_id = s.wholesaler_id
         AND pw.brand_code = s.brand_code AND pw.prc_code = s.prc_code AND pw.week_number = s.week_number
    """)
    meta = {(r["wholesaler_id"], r["brand_code"], r["prc_code"], int(_num(r["week_number"]))): r for r in rows}

    total = out["total_discount"]
    n_weeks = out["n_promo_weeks"]
    new_promo_lines: set[tuple] = set()
    for e in edits:
        key = (e["wholesaler_id"], e["brand_code"], e["prc_code"], int(e["week_number"]))
        m = meta.get(key)
        if not m:
            continue
        base = _num(m["base_pptr"]) or 0.0
        old_rec = _num(m["old_rec"])
        new_off = e["absolute_discount"] if e["absolute_discount"] is not None else (e["incremental_discount"] or 0.0)
        old_off = (base - old_rec) if old_rec is not None else 0.0
        total += new_off - old_off
        if old_rec is None:
            n_weeks += 1                       # a brand-new promo week
            if (_num(m["line_prod_weeks"]) or 0) == 0:
                new_promo_lines.add((e["wholesaler_id"], e["brand_code"], e["prc_code"]))

    out["total_discount"] = round(total, 2)
    out["n_promo_weeks"] = n_weeks
    out["n_lines_on_promo"] = out["n_lines_on_promo"] + len(new_promo_lines)
    out["avg_incremental_discount"] = round(total / n_weeks, 4) if n_weeks else 0.0
    return out


@router.get("/pricing/final")
async def final_plan_export(
    request: Request,
    wholesaler: str | None = None,
    brand: str | None = None,
    prc_group: str | None = None,
    limit: int = Query(500, le=5000),
):
    """Downstream API: the finally-approved 2027 pricing as clean JSON.

    This is the "call an API to gather this info" ask — the payload another
    application pulls once pricing is finally approved. Returns approved
    fact_promo_week rows joined to their line metadata.
    """
    where = _line_where(2027, wholesaler, brand, prc_group, alias="l")
    rows = await run_query(request, f"""
        SELECT l.wholesaler_id, l.wholesaler_name, l.brand_code, l.brand_name,
               l.prc_code, l.prc_group_name, l.deal_description, l.base_pptr,
               pw.week_number, pw.incremental_discount, pw.absolute_discount,
               pw.rec_pptr, pw.approval_status
        FROM {FQ}.fact_price_plan l
        JOIN {FQ}.fact_promo_week pw
          ON pw.plan_year = l.plan_year AND pw.wholesaler_id = l.wholesaler_id
         AND pw.brand_code = l.brand_code AND pw.prc_code = l.prc_code
        WHERE {where} AND pw.approval_status = 'approved'
        ORDER BY l.wholesaler_id, l.brand_code, l.prc_code, pw.week_number
        LIMIT {int(limit)}
    """)
    numeric = ("week_number", "incremental_discount", "absolute_discount", "rec_pptr", "base_pptr")
    for r in rows:
        for k in numeric:
            r[k] = _num(r.get(k))
    return {
        "plan_year": 2027,
        "status": "approved",
        "count": len(rows),
        "pricing": rows,
    }


# Production ("main records") tables in Unity Catalog, for the info panel.
_UC_TABLES = [
    {"table": "fact_price_plan", "grain": "plan_year × wholesaler × brand × PRC group",
     "purpose": "The dense grid lines — every wholesale price line with its base REC PPTR and current max discount. This is the 'row' the business counts (~1.3M in prod)."},
    {"table": "fact_promo_week", "grain": "line × ISO week",
     "purpose": "Single source of truth for per-week promo overrides (dollars off + resulting REC PPTR) with approval_status: committed (2026), pending (submitted), approved (Final Plan). Submit MERGEs edits here; Final Submission flips them to 'approved' — visible immediately in the app."},
    {"table": "dim_wholesaler", "grain": "wholesaler", "purpose": "Wholesaler / distributor reference (id, name, region, state)."},
    {"table": "dim_brand", "grain": "brand", "purpose": "Brand code → brand name."},
    {"table": "dim_prc_group", "grain": "PRC group", "purpose": "Product/pack group with QD thresholds and deal description."},
    {"table": "dim_iso_week", "grain": "week", "purpose": "The 52 ISO weeks that form the grid's column axis."},
]


@router.get("/pricing/catalog-info")
async def catalog_info(request: Request):
    """Live snapshot of how the 'main' pricing records are stored in Unity Catalog:
    catalog/schema/warehouse, the production tables with purpose and current row
    counts, and the sandbox→submit→approve lifecycle. Powers the 'Main records' panel."""
    counts: dict[str, int] = {}
    try:
        union = " UNION ALL ".join(
            f"SELECT '{t['table']}' AS tbl, count(*) AS n FROM {FQ}.{t['table']}" for t in _UC_TABLES
        )
        rows = await run_query(request, union)
        for r in rows:
            counts[r["tbl"]] = int(_num(r["n"]))
        status = "connected"
    except Exception as e:
        status = f"error: {e}"
    return {
        "engine": "Unity Catalog (Delta) via Databricks SQL",
        "catalog": PROMO_CATALOG,
        "schema": PROMO_SCHEMA,
        "warehouse_id": DEFAULT_WAREHOUSE_ID,
        "status": status,
        "role_summary": "Governed system of record for all pricing. Grid reads come from here; approved changes are the source of truth handed downstream.",
        "tables": [dict(t, rows=counts.get(t["table"])) for t in _UC_TABLES],
        "lifecycle": [
            {"stage": "Edit", "where": "Lakebase (sandbox)", "detail": "Coordinators edit cells; nothing in UC changes yet."},
            {"stage": "Submit for Review", "where": "→ Unity Catalog", "detail": "Sandbox edits MERGE into fact_promo_week as approval_status = 'pending'."},
            {"stage": "Final Submission", "where": "Unity Catalog", "detail": "CSO approval flips rows to 'approved' — the Final Plan."},
            {"stage": "Downstream", "where": "GET /api/pricing/final", "detail": "Approved rows served as JSON to the Pricing Hub."},
        ],
    }

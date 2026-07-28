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
from server.routes.sql_exec import run_query, FQ

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
        clauses.append(f"{p}wholesaler_id = '{_esc(wholesaler)}'")
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
        LEFT JOIN {FQ}.fact_promo_week pw
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

    # Overlay Lakebase sandbox edits (in-progress, unsubmitted) onto matching cells.
    if sandbox_id:
        from server.routes.planning import get_sandbox_edits
        edits = await get_sandbox_edits(sandbox_id, plan_year)
        for e in edits:
            key = f"{e['wholesaler_id']}|{e['brand_code']}|{e['prc_code']}"
            line = lines.get(key)
            if line is None:
                continue  # edit is outside this page
            base = line["base_pptr"]
            inc = e.get("incremental_discount")
            absd = e.get("absolute_discount")
            rec = (base - absd) if absd is not None else (base * (1 - inc) if inc is not None else base)
            line["cells"][str(e["week_number"])] = {
                "week": e["week_number"],
                "incremental_discount": inc,
                "absolute_discount": absd,
                "rec_pptr": round(rec, 2),
                "approval_status": "sandbox",
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
):
    """Portfolio budget roll-up over the filtered set, for the always-on budget bar.

    Total discount $ = sum(base_pptr - rec_pptr) over promo weeks; plus line count,
    promo-week count, and lines-on-promo. One cheap aggregate query (not paged).
    """
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
        JOIN {FQ}.fact_promo_week pw
          ON pw.plan_year = {int(plan_year)} AND pw.wholesaler_id = l.wholesaler_id
         AND pw.brand_code = l.brand_code AND pw.prc_code = l.prc_code
    """)
    r = agg[0] if agg else {}
    return {k: _num(v) for k, v in r.items()}


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

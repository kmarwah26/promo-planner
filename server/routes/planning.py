"""Write-back routes backed by Lakebase (Postgres) + Unity Catalog.

The Promo 1YP data flow is: edit in a low-latency **sandbox** (Lakebase), then
**submit** to promote those edits into the governed **production** table in Unity
Catalog, where the CSO team **approves** them for the Final Plan.

- Sandbox edits (per-cell incremental/absolute discounts) live in Lakebase for
  fast, multi-user, in-progress editing. Multiple users can edit concurrently;
  each edit records who made it.
- Submit MERGEs the sandbox rows into UC `fact_promo_week` (the single source
  table, status 'pending') and clears them from the sandbox.
- Approve flips submitted 2027 rows to 'approved' (Final Plan).
- Reset clears all sandbox edits for a filter (the "revert all" button).
"""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from server.db import db
from server.routes.sql_exec import run_query, FQ

router = APIRouter(tags=["planning"])

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS plan_edit (
    sandbox_id TEXT NOT NULL,
    plan_year INT NOT NULL,
    wholesaler_id TEXT NOT NULL,
    brand_code TEXT NOT NULL,
    prc_code TEXT NOT NULL,
    week_number INT NOT NULL,
    incremental_discount DOUBLE PRECISION,
    absolute_discount DOUBLE PRECISION,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sandbox_id, plan_year, wholesaler_id, brand_code, prc_code, week_number)
);
CREATE INDEX IF NOT EXISTS idx_plan_edit_sandbox ON plan_edit (sandbox_id, plan_year);
CREATE TABLE IF NOT EXISTS plan_activity (
    id TEXT PRIMARY KEY,
    sandbox_id TEXT,
    actor TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plan_activity_sandbox ON plan_activity (sandbox_id, created_at DESC);
CREATE TABLE IF NOT EXISTS plan_review (
    sandbox_id TEXT NOT NULL,
    plan_year INT NOT NULL,
    line_key TEXT NOT NULL,        -- "wholesaler_id|brand_code|prc_code"
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sandbox_id, plan_year, line_key)
);
CREATE INDEX IF NOT EXISTS idx_plan_review_sandbox ON plan_review (sandbox_id, plan_year);
CREATE TABLE IF NOT EXISTS uc_promo_week_mirror (
    plan_year INT NOT NULL,
    wholesaler_id TEXT NOT NULL,
    brand_code TEXT NOT NULL,
    prc_code TEXT NOT NULL,
    week_number INT NOT NULL,
    incremental_discount DOUBLE PRECISION,
    absolute_discount DOUBLE PRECISION,
    rec_pptr DOUBLE PRECISION,
    approval_status TEXT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (plan_year, wholesaler_id, brand_code, prc_code, week_number)
);
CREATE TABLE IF NOT EXISTS plan_sync_log (
    id TEXT PRIMARY KEY,
    direction TEXT NOT NULL,     -- 'Lakebase → Unity Catalog' | 'Unity Catalog → Lakebase'
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    rows INT NOT NULL,
    duration_ms INT,
    detail TEXT,
    actor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plan_sync_created ON plan_sync_log (created_at DESC);
"""

_ready = False


async def _ensure_tables():
    global _ready
    if _ready:
        return
    pool = await db.get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(CREATE_SQL)
        _ready = True
    except Exception as e:
        print(f"[planning] table create failed: {e}")


def _actor(request: Request | None) -> str:
    if request is None:
        return "unknown"
    return (
        request.headers.get("X-Forwarded-Email")
        or request.headers.get("X-Forwarded-Preferred-Username")
        or "demo-user"
    )


async def _log(conn, sandbox_id: str, actor: str, action: str, detail: str = ""):
    await conn.execute(
        "INSERT INTO plan_activity (id, sandbox_id, actor, action, detail) VALUES ($1,$2,$3,$4,$5)",
        uuid.uuid4().hex, sandbox_id, actor, action, detail,
    )


async def _log_sync(direction: str, source: str, target: str, rows: int,
                    duration_ms: int, detail: str, actor: str):
    """Record a UC↔Lakebase sync event (best-effort; never raises)."""
    pool = await db.get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO plan_sync_log (id, direction, source, target, rows, duration_ms, detail, actor)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                uuid.uuid4().hex, direction, source, target, rows, duration_ms, detail, actor,
            )
    except Exception as e:
        print(f"[sync] log failed: {e}")


async def mirror_uc_to_lakebase(request: Request, cells: list[dict], plan_year: int, actor: str):
    """Unity Catalog → Lakebase: after edits land in UC, read those exact rows back
    from UC and mirror them into the Lakebase `uc_promo_week_mirror` table. This makes
    the round-trip visible in the demo (UC is the source of truth; Lakebase keeps a
    fast local copy). Best-effort; logs a sync event with row count + duration."""
    import time as _time
    pool = await db.get_pool()
    if not pool or not cells:
        return
    start = _time.monotonic()
    # Read the affected rows back from UC.
    keys = ",".join(
        f"('{c['wholesaler_id']}','{c['brand_code']}','{c['prc_code']}',{int(c['week_number'])})"
        for c in cells
    )
    rows = await run_query(request, f"""
        SELECT pw.plan_year, pw.wholesaler_id, pw.brand_code, pw.prc_code, pw.week_number,
               pw.incremental_discount, pw.absolute_discount, pw.rec_pptr, pw.approval_status
        FROM {FQ}.fact_promo_week pw
        JOIN (SELECT * FROM (VALUES {keys}) AS k(wholesaler_id, brand_code, prc_code, week_number)) k
          ON pw.wholesaler_id = k.wholesaler_id AND pw.brand_code = k.brand_code
         AND pw.prc_code = k.prc_code AND pw.week_number = k.week_number
        WHERE pw.plan_year = {int(plan_year)}
    """)

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """INSERT INTO uc_promo_week_mirror
                         (plan_year, wholesaler_id, brand_code, prc_code, week_number,
                          incremental_discount, absolute_discount, rec_pptr, approval_status, synced_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, NOW())
                       ON CONFLICT (plan_year, wholesaler_id, brand_code, prc_code, week_number)
                       DO UPDATE SET incremental_discount = EXCLUDED.incremental_discount,
                                     absolute_discount = EXCLUDED.absolute_discount,
                                     rec_pptr = EXCLUDED.rec_pptr,
                                     approval_status = EXCLUDED.approval_status,
                                     synced_at = NOW()""",
                    [(int(_num_i(r["plan_year"])), r["wholesaler_id"], r["brand_code"], r["prc_code"],
                      int(_num_i(r["week_number"])), _f(r["incremental_discount"]), _f(r["absolute_discount"]),
                      _f(r["rec_pptr"]), r["approval_status"]) for r in rows],
                )
        dur = int((_time.monotonic() - start) * 1000)
        await _log_sync("Unity Catalog → Lakebase", f"{FQ}.fact_promo_week", "uc_promo_week_mirror",
                        len(rows), dur, f"Mirrored {len(rows)} approved/updated row(s) back to Lakebase", actor)
    except Exception as e:
        print(f"[sync] UC→Lakebase mirror failed: {e}")


def _num_i(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


# ── Helper used by pricing.py to overlay sandbox edits on the grid ──

async def get_sandbox_edits(sandbox_id: str, plan_year: int) -> list[dict]:
    """All sandbox edits for a sandbox + plan year (empty if DB unavailable)."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT wholesaler_id, brand_code, prc_code, week_number,
                          incremental_discount, absolute_discount
                   FROM plan_edit WHERE sandbox_id = $1 AND plan_year = $2""",
                sandbox_id, plan_year,
            )
        return [
            {"wholesaler_id": r["wholesaler_id"], "brand_code": r["brand_code"],
             "prc_code": r["prc_code"], "week_number": r["week_number"],
             "incremental_discount": r["incremental_discount"],
             "absolute_discount": r["absolute_discount"]}
            for r in rows
        ]
    except Exception:
        return []


async def get_reviewed_keys(sandbox_id: str, plan_year: int) -> set[str]:
    """Set of line_keys marked reviewed in this sandbox + plan year."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return set()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT line_key FROM plan_review WHERE sandbox_id = $1 AND plan_year = $2",
                sandbox_id, plan_year,
            )
        return {r["line_key"] for r in rows}
    except Exception:
        return set()


# ── Write-back endpoints ──

class CellEdit(BaseModel):
    wholesaler_id: str
    brand_code: str
    prc_code: str
    week_number: int
    incremental_discount: float | None = None
    absolute_discount: float | None = None


class EditRequest(BaseModel):
    sandbox_id: str
    plan_year: int = 2027
    edits: list[CellEdit]


@router.post("/planning/edit")
async def save_edits(req: EditRequest, request: Request):
    """Upsert one or many cell edits into the sandbox.

    Accepts a bulk list so the UI can apply an absolute/incremental discount
    across many selected rows × weeks in a single call (mass-select workflow).
    """
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")
    if not req.edits:
        return {"ok": True, "written": 0}
    actor = _actor(request)
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO plan_edit (sandbox_id, plan_year, wholesaler_id, brand_code,
                    prc_code, week_number, incremental_discount, absolute_discount, updated_by, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (sandbox_id, plan_year, wholesaler_id, brand_code, prc_code, week_number)
                DO UPDATE SET incremental_discount = EXCLUDED.incremental_discount,
                              absolute_discount = EXCLUDED.absolute_discount,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = EXCLUDED.updated_at
                """,
                [(req.sandbox_id, req.plan_year, e.wholesaler_id, e.brand_code, e.prc_code,
                  e.week_number, e.incremental_discount, e.absolute_discount, actor, now)
                 for e in req.edits],
            )
            kind = "absolute" if any(e.absolute_discount is not None for e in req.edits) else "incremental"
            await _log(conn, req.sandbox_id, actor, "edit",
                       f"{len(req.edits)} cell(s) — {kind} discount")
    writes = [{
        "table": "plan_edit", "operation": "UPSERT",
        "row_key": f"sandbox_id = {req.sandbox_id}",
        "columns": {"cells": len(req.edits), "plan_year": req.plan_year, "updated_by": actor},
    }]
    return {
        "ok": True, "written": len(req.edits),
        "lakebase": {
            "database": os.environ.get("PGDATABASE", "promo_planner"),
            "instance": os.environ.get("LAKEBASE_INSTANCE", "lakebase-demo"),
            "writes": writes,
        },
    }


class ReviewRequest(BaseModel):
    sandbox_id: str
    plan_year: int = 2027
    line_keys: list[str]
    reviewed: bool = True


@router.post("/planning/review")
async def mark_reviewed(req: ReviewRequest, request: Request):
    """Mark (or unmark) one or many grid lines as reviewed by a regional coordinator.

    Reviewing is a lightweight per-line flag (kept in Lakebase) that coordinators set
    before the plan is submitted to the central CSO team. Bulk list supports the
    'review selected rows' action.
    """
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")
    if not req.line_keys:
        return {"ok": True, "reviewed": 0}
    actor = _actor(request)
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        async with conn.transaction():
            if req.reviewed:
                await conn.executemany(
                    """INSERT INTO plan_review (sandbox_id, plan_year, line_key, reviewed_by, reviewed_at)
                       VALUES ($1,$2,$3,$4,$5)
                       ON CONFLICT (sandbox_id, plan_year, line_key)
                       DO UPDATE SET reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at""",
                    [(req.sandbox_id, req.plan_year, k, actor, now) for k in req.line_keys],
                )
                await _log(conn, req.sandbox_id, actor, "review", f"Marked {len(req.line_keys)} line(s) reviewed")
            else:
                await conn.execute(
                    "DELETE FROM plan_review WHERE sandbox_id = $1 AND plan_year = $2 AND line_key = ANY($3::text[])",
                    req.sandbox_id, req.plan_year, req.line_keys,
                )
                await _log(conn, req.sandbox_id, actor, "unreview", f"Cleared review on {len(req.line_keys)} line(s)")
    return {"ok": True, "reviewed": len(req.line_keys) if req.reviewed else 0}


class ResetRequest(BaseModel):
    sandbox_id: str
    plan_year: int = 2027


@router.post("/planning/reset")
async def reset_sandbox(req: ResetRequest, request: Request):
    """Revert all: delete every sandbox edit for this sandbox + plan year."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")
    async with pool.acquire() as conn:
        res = await conn.execute(
            "DELETE FROM plan_edit WHERE sandbox_id = $1 AND plan_year = $2",
            req.sandbox_id, req.plan_year,
        )
        await conn.execute(
            "DELETE FROM plan_review WHERE sandbox_id = $1 AND plan_year = $2",
            req.sandbox_id, req.plan_year,
        )
        await _log(conn, req.sandbox_id, _actor(request), "reset", "Reverted all sandbox edits")
    # res is like "DELETE <n>"
    deleted = int(res.split()[-1]) if res and res.split()[-1].isdigit() else 0
    return {"ok": True, "deleted": deleted}


class SubmitRequest(BaseModel):
    sandbox_id: str
    plan_year: int = 2027


@router.post("/planning/submit")
async def submit_sandbox(req: SubmitRequest, request: Request):
    """Promote sandbox edits → production.

    MERGEs the Lakebase sandbox rows into UC `fact_promo_week` (status 'pending'),
    recomputing rec_pptr from the line's base price, then clears the submitted
    sandbox rows. Returns a write summary describing what was persisted where.
    """
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")

    edits = await get_sandbox_edits(req.sandbox_id, req.plan_year)
    if not edits:
        return {"ok": True, "submitted": 0, "detail": "Nothing to submit"}

    # Build a VALUES list to MERGE into UC. rec_pptr is derived from base_pptr in the
    # target table (absolute overrides incremental).
    def _v(x):
        return "NULL" if x is None else str(x)
    values = ",\n".join(
        f"('{e['wholesaler_id']}','{e['brand_code']}','{e['prc_code']}',{int(e['week_number'])},"
        f"{_v(e['incremental_discount'])},{_v(e['absolute_discount'])})"
        for e in edits
    )
    merge_sql = f"""
        MERGE INTO {FQ}.fact_promo_week t
        USING (
          SELECT s.wholesaler_id, s.brand_code, s.prc_code, s.week_number,
                 s.incremental_discount, s.absolute_discount,
                 -- both discounts are dollars off per case
                 round(p.base_pptr - coalesce(s.absolute_discount, s.incremental_discount, 0), 2) AS rec_pptr
          FROM (VALUES {values})
            AS s(wholesaler_id, brand_code, prc_code, week_number, incremental_discount, absolute_discount)
          JOIN {FQ}.fact_price_plan p
            ON p.plan_year = {int(req.plan_year)} AND p.wholesaler_id = s.wholesaler_id
           AND p.brand_code = s.brand_code AND p.prc_code = s.prc_code
        ) s
        ON  t.plan_year = {int(req.plan_year)} AND t.wholesaler_id = s.wholesaler_id
        AND t.brand_code = s.brand_code AND t.prc_code = s.prc_code AND t.week_number = s.week_number
        WHEN MATCHED THEN UPDATE SET
          incremental_discount = s.incremental_discount,
          absolute_discount = s.absolute_discount,
          rec_pptr = s.rec_pptr,
          approval_status = 'pending'
        WHEN NOT MATCHED THEN INSERT
          (plan_year, wholesaler_id, brand_code, prc_code, week_number,
           incremental_discount, absolute_discount, rec_pptr, approval_status)
          VALUES ({int(req.plan_year)}, s.wholesaler_id, s.brand_code, s.prc_code, s.week_number,
                  s.incremental_discount, s.absolute_discount, s.rec_pptr, 'pending')
    """
    import time as _time
    _t0 = _time.monotonic()
    await run_query(request, merge_sql)
    _merge_ms = int((_time.monotonic() - _t0) * 1000)
    actor = _actor(request)

    # Sync event 1: Lakebase → Unity Catalog (the edits we just MERGEd).
    await _log_sync("Lakebase → Unity Catalog", "plan_edit (sandbox)", f"{FQ}.fact_promo_week",
                    len(edits), _merge_ms, f"Submitted {len(edits)} cell(s) → status 'pending'", actor)
    # Sync event 2: Unity Catalog → Lakebase (mirror the resulting rows back).
    await mirror_uc_to_lakebase(request, edits, req.plan_year, actor)

    # Clear the submitted sandbox rows and log.
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM plan_edit WHERE sandbox_id = $1 AND plan_year = $2",
            req.sandbox_id, req.plan_year,
        )
        await conn.execute(
            "DELETE FROM plan_review WHERE sandbox_id = $1 AND plan_year = $2",
            req.sandbox_id, req.plan_year,
        )
        await _log(conn, req.sandbox_id, actor, "submit",
                   f"Submitted {len(edits)} cell(s) to production (pending approval)")

    return {
        "ok": True,
        "submitted": len(edits),
        "writes": [
            {"target": "Unity Catalog", "table": f"{FQ}.fact_promo_week",
             "operation": "MERGE", "detail": f"{len(edits)} promo-week cell(s) → status 'pending'"},
            {"target": "Lakebase", "table": "plan_edit",
             "operation": "DELETE", "detail": "sandbox edits cleared after submit"},
        ],
    }


class ApproveRequest(BaseModel):
    plan_year: int = 2027
    wholesaler: str | None = None
    brand: str | None = None
    prc_group: str | None = None


@router.post("/planning/approve")
async def approve_final(req: ApproveRequest, request: Request):
    """CSO approval: flip submitted 2027 rows from 'pending' to 'approved' (Final Plan)."""
    clauses = [f"plan_year = {int(req.plan_year)}", "approval_status = 'pending'"]
    if req.wholesaler:
        ids = [w.strip().replace(chr(39), chr(39)*2) for w in str(req.wholesaler).split(",") if w.strip()]
        if len(ids) == 1:
            clauses.append(f"wholesaler_id = '{ids[0]}'")
        elif ids:
            clauses.append("wholesaler_id IN (" + ",".join(f"'{w}'" for w in ids) + ")")
    if req.brand:
        clauses.append(f"brand_code = '{req.brand.replace(chr(39), chr(39)*2)}'")
    if req.prc_group:
        clauses.append(f"prc_code = '{req.prc_group.replace(chr(39), chr(39)*2)}'")
    where = " AND ".join(clauses)
    # Capture the keys we're about to approve so we can mirror them back to Lakebase.
    pending = await run_query(request, f"""
        SELECT wholesaler_id, brand_code, prc_code, week_number
        FROM {FQ}.fact_promo_week WHERE {where}
    """)
    import time as _time
    _t0 = _time.monotonic()
    await run_query(request, f"""
        UPDATE {FQ}.fact_promo_week SET approval_status = 'approved' WHERE {where}
    """)
    _upd_ms = int((_time.monotonic() - _t0) * 1000)
    actor = _actor(request)
    n = len(pending)

    pool = await db.get_pool()
    if pool:
        async with pool.acquire() as conn:
            await _log(conn, "final", actor, "approve", f"Approved {n} row(s) where {where}")
    # Sync events: the approval (Lakebase-driven action → UC) and the mirror back.
    await _log_sync("Lakebase → Unity Catalog", "Final Submission (approve)", f"{FQ}.fact_promo_week",
                    n, _upd_ms, f"Approved {n} pending row(s) → 'approved'", actor)
    if pending:
        cells = [{"wholesaler_id": r["wholesaler_id"], "brand_code": r["brand_code"],
                  "prc_code": r["prc_code"], "week_number": int(_num_i(r["week_number"]))} for r in pending]
        await mirror_uc_to_lakebase(request, cells, req.plan_year, actor)
    return {"ok": True, "approved": n}


@router.get("/planning/activity/recent")
async def recent_activity():
    """Recent sandbox/submit/approve activity (for a status feed)."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return {"activity": [], "db_available": False}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT sandbox_id, actor, action, detail, created_at FROM plan_activity ORDER BY created_at DESC LIMIT 30"
        )
    return {
        "activity": [
            {"sandbox_id": r["sandbox_id"], "actor": r["actor"], "action": r["action"],
             "detail": r["detail"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ],
        "db_available": True,
    }


# Descriptions of the Lakebase sandbox tables, shown in the "How Lakebase is used" panel.
_LAKEBASE_TABLES = [
    {"table": "plan_edit",
     "purpose": "In-progress 2027 discount edits, one row per (sandbox, line, week). Written on every cell edit / mass apply; overlaid on the grid at read time; cleared on Submit or Reset."},
    {"table": "plan_review",
     "purpose": "Per-line 'reviewed' flags set by regional coordinators before submission (per-row and bulk). Cleared on Submit or Reset."},
    {"table": "plan_activity",
     "purpose": "Append-only audit log of every edit, review, reset, submit and approve — who did what, when."},
    {"table": "uc_promo_week_mirror",
     "purpose": "Unity Catalog → Lakebase mirror: a fast local copy of the UC promo rows touched by Submit / Final Submission, kept in sync on every write."},
    {"table": "plan_sync_log",
     "purpose": "Record of every UC↔Lakebase sync (direction, rows, duration) — powers the sync feed below."},
]


@router.get("/planning/lakebase-info")
async def lakebase_info():
    """Live snapshot of how Lakebase (Postgres) is being used: connection details,
    the sandbox tables with their purpose and current row counts, and a recent
    activity feed. Powers the 'How Lakebase is used' side panel."""
    await _ensure_tables()
    host = os.environ.get("PGHOST", "")
    info = {
        "engine": "Lakebase (managed Postgres)",
        "instance": os.environ.get("LAKEBASE_INSTANCE", "lakebase-demo"),
        "database": os.environ.get("PGDATABASE", "promo_planner"),
        "host": host,
        "role": "app service principal",
        "status": "disconnected",
        "role_summary": "Low-latency operational store for in-progress edits — the sandbox layer, separate from the governed analytical data in Unity Catalog.",
        "tables": [dict(t, rows=None) for t in _LAKEBASE_TABLES],
        "activity": [],
        "syncs": [],
    }
    pool = await db.get_pool()
    if not pool:
        return info
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            info["status"] = "connected"
            for t in info["tables"]:
                try:
                    t["rows"] = await conn.fetchval(f"SELECT count(*) FROM {t['table']}")
                except Exception:
                    t["rows"] = None
            rows = await conn.fetch(
                "SELECT actor, action, detail, created_at FROM plan_activity ORDER BY created_at DESC LIMIT 8"
            )
            info["activity"] = [
                {"actor": r["actor"], "action": r["action"], "detail": r["detail"],
                 "created_at": r["created_at"].isoformat()}
                for r in rows
            ]
            try:
                srows = await conn.fetch(
                    """SELECT direction, source, target, rows, duration_ms, detail, created_at
                       FROM plan_sync_log ORDER BY created_at DESC LIMIT 8"""
                )
                info["syncs"] = [
                    {"direction": r["direction"], "source": r["source"], "target": r["target"],
                     "rows": r["rows"], "duration_ms": r["duration_ms"], "detail": r["detail"],
                     "created_at": r["created_at"].isoformat()}
                    for r in srows
                ]
            except Exception:
                info["syncs"] = []
    except Exception as e:
        info["status"] = f"error: {e}"
    return info

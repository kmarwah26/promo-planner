"""Write-back routes backed by Lakebase (Postgres) + Unity Catalog.

The Promo 1YP data flow is: edit in a low-latency **sandbox** (Lakebase), then
**submit** to promote those edits into the governed **production** table in Unity
Catalog, where the CSO team **approves** them for the Final Plan.

- Sandbox edits (per-cell incremental/absolute discounts) live in Lakebase for
  fast, multi-user, in-progress editing. Multiple users can edit concurrently;
  each edit records who made it.
- Submit MERGEs the sandbox rows into UC `fact_promo_week` (plan_year 2027,
  status 'pending') and clears them from the sandbox.
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
                 CASE WHEN s.absolute_discount IS NOT NULL
                      THEN round(p.base_pptr - s.absolute_discount, 2)
                      ELSE round(p.base_pptr * (1 - coalesce(s.incremental_discount, 0)), 2) END AS rec_pptr
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
    await run_query(request, merge_sql)

    # Clear the submitted sandbox rows and log.
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM plan_edit WHERE sandbox_id = $1 AND plan_year = $2",
            req.sandbox_id, req.plan_year,
        )
        await _log(conn, req.sandbox_id, _actor(request), "submit",
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
        clauses.append(f"wholesaler_id = '{req.wholesaler.replace(chr(39), chr(39)*2)}'")
    if req.brand:
        clauses.append(f"brand_code = '{req.brand.replace(chr(39), chr(39)*2)}'")
    if req.prc_group:
        clauses.append(f"prc_code = '{req.prc_group.replace(chr(39), chr(39)*2)}'")
    where = " AND ".join(clauses)
    await run_query(request, f"""
        UPDATE {FQ}.fact_promo_week SET approval_status = 'approved' WHERE {where}
    """)
    pool = await db.get_pool()
    if pool:
        async with pool.acquire() as conn:
            await _log(conn, "final", _actor(request), "approve", f"Approved 2027 plan where {where}")
    return {"ok": True}


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

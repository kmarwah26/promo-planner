"""Write-back routes backed by Lakebase (Postgres).

These persist the operational state a revenue manager creates while planning:
plan status (approve / lock), budget adjustments, follow-up assignments, and comments.
This is the transactional layer that sits alongside the analytical Unity Catalog data.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from server.db import db

router = APIRouter(tags=["planning"])

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS promo_plan_state (
    promotion_id TEXT PRIMARY KEY,
    status TEXT,                       -- Draft | Proposed | Approved | Locked
    adjusted_budget DOUBLE PRECISION,  -- overridden trade-spend budget
    adjusted_discount DOUBLE PRECISION,-- scenario discount depth (fraction, e.g. 0.15)
    assigned_to TEXT,                  -- follow-up owner email/name
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE promo_plan_state ADD COLUMN IF NOT EXISTS adjusted_discount DOUBLE PRECISION;
CREATE TABLE IF NOT EXISTS promo_comments (
    id TEXT PRIMARY KEY,
    promotion_id TEXT NOT NULL,
    author TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_promo_comments_pid ON promo_comments (promotion_id, created_at DESC);
CREATE TABLE IF NOT EXISTS promo_activity (
    id TEXT PRIMARY KEY,
    promotion_id TEXT NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_promo_activity_pid ON promo_activity (promotion_id, created_at DESC);
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


async def _log(conn, promotion_id: str, actor: str, action: str, detail: str = ""):
    await conn.execute(
        "INSERT INTO promo_activity (id, promotion_id, actor, action, detail) VALUES ($1,$2,$3,$4,$5)",
        uuid.uuid4().hex, promotion_id, actor, action, detail,
    )


# ── Helpers used by promos.py to overlay state onto analytical rows ──

async def get_plan_state_map() -> dict:
    """All plan-state rows keyed by promotion_id (empty dict if DB unavailable)."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return {}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM promo_plan_state")
        return {r["promotion_id"]: _state_dict(r) for r in rows}
    except Exception:
        return {}


async def get_plan_state(promotion_id: str):
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return None
    try:
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT * FROM promo_plan_state WHERE promotion_id = $1", promotion_id)
        return _state_dict(r) if r else None
    except Exception:
        return None


async def list_comments(promotion_id: str):
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, author, body, created_at FROM promo_comments WHERE promotion_id = $1 ORDER BY created_at DESC",
                promotion_id,
            )
        return [
            {"id": r["id"], "author": r["author"], "body": r["body"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ]
    except Exception:
        return []


def _state_dict(r) -> dict:
    return {
        "promotion_id": r["promotion_id"],
        "status": r["status"],
        "adjusted_budget": r["adjusted_budget"],
        "adjusted_discount": r["adjusted_discount"],
        "assigned_to": r["assigned_to"],
        "locked": r["locked"],
        "updated_by": r["updated_by"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


async def _upsert_state(request: Request, promotion_id: str, **fields):
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")
    actor = _actor(request)
    cols = ["status", "adjusted_budget", "adjusted_discount", "assigned_to", "locked"]
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM promo_plan_state WHERE promotion_id = $1", promotion_id)
        merged = {c: (existing[c] if existing else None) for c in cols}
        if not existing:
            merged["locked"] = False
        for k, v in fields.items():
            merged[k] = v
        await conn.execute(
            """
            INSERT INTO promo_plan_state (promotion_id, status, adjusted_budget, adjusted_discount, assigned_to, locked, updated_by, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (promotion_id) DO UPDATE SET
              status = EXCLUDED.status,
              adjusted_budget = EXCLUDED.adjusted_budget,
              adjusted_discount = EXCLUDED.adjusted_discount,
              assigned_to = EXCLUDED.assigned_to,
              locked = EXCLUDED.locked,
              updated_by = EXCLUDED.updated_by,
              updated_at = EXCLUDED.updated_at
            """,
            promotion_id, merged["status"], merged["adjusted_budget"], merged["adjusted_discount"],
            merged["assigned_to"], bool(merged["locked"]), actor, datetime.now(timezone.utc),
        )
        return await conn.fetchrow("SELECT * FROM promo_plan_state WHERE promotion_id = $1", promotion_id)


# ── Write-back endpoints ──

class ApproveRequest(BaseModel):
    promotion_id: str


@router.post("/planning/approve")
async def approve(req: ApproveRequest, request: Request):
    r = await _upsert_state(request, req.promotion_id, status="Approved")
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await _log(conn, req.promotion_id, _actor(request), "approve", "Plan approved")
    return {"ok": True, "state": _state_dict(r)}


class ScenarioRequest(BaseModel):
    promotion_id: str
    adjusted_discount: float          # scenario discount depth as a fraction (e.g. 0.15)
    adjusted_budget: float | None = None  # recomputed trade-spend at that discount


@router.post("/planning/scenario")
async def save_scenario(req: ScenarioRequest, request: Request):
    """Save a scenario edit from the grid: the proposed discount depth (and the
    trade-spend budget it implies). Marks the plan Proposed if it was still a Draft."""
    r = await _upsert_state(
        request, req.promotion_id,
        adjusted_discount=req.adjusted_discount,
        adjusted_budget=req.adjusted_budget,
    )
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await _log(conn, req.promotion_id, _actor(request), "scenario",
                   f"Discount set to {req.adjusted_discount:.0%}"
                   + (f", budget {req.adjusted_budget:,.0f}" if req.adjusted_budget is not None else ""))
    return {"ok": True, "state": _state_dict(r)}


class LockRequest(BaseModel):
    promotion_id: str
    locked: bool = True


@router.post("/planning/lock")
async def lock(req: LockRequest, request: Request):
    r = await _upsert_state(request, req.promotion_id, locked=req.locked,
                            status="Locked" if req.locked else "Approved")
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await _log(conn, req.promotion_id, _actor(request), "lock" if req.locked else "unlock",
                   "Scenario locked" if req.locked else "Scenario unlocked")
    return {"ok": True, "state": _state_dict(r)}


class BudgetRequest(BaseModel):
    promotion_id: str
    adjusted_budget: float


@router.post("/planning/budget")
async def adjust_budget(req: BudgetRequest, request: Request):
    r = await _upsert_state(request, req.promotion_id, adjusted_budget=req.adjusted_budget)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await _log(conn, req.promotion_id, _actor(request), "adjust_budget",
                   f"Trade-spend budget set to {req.adjusted_budget:,.0f}")
    return {"ok": True, "state": _state_dict(r)}


class AssignRequest(BaseModel):
    promotion_id: str
    assigned_to: str


@router.post("/planning/assign")
async def assign(req: AssignRequest, request: Request):
    r = await _upsert_state(request, req.promotion_id, assigned_to=req.assigned_to)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await _log(conn, req.promotion_id, _actor(request), "assign", f"Follow-up assigned to {req.assigned_to}")
    return {"ok": True, "state": _state_dict(r)}


class CommentRequest(BaseModel):
    promotion_id: str
    body: str


@router.post("/planning/comment")
async def add_comment(req: CommentRequest, request: Request):
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Lakebase not available — write-back disabled")
    cid = uuid.uuid4().hex
    author = _actor(request)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promo_comments (id, promotion_id, author, body) VALUES ($1,$2,$3,$4)",
            cid, req.promotion_id, author, req.body,
        )
        await _log(conn, req.promotion_id, author, "comment", req.body[:120])
    return {"ok": True, "id": cid}


@router.get("/planning/{promotion_id}/comments")
async def get_comments(promotion_id: str):
    return {"comments": await list_comments(promotion_id)}


@router.get("/planning/{promotion_id}/activity")
async def get_activity(promotion_id: str):
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return {"activity": [], "db_available": False}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT actor, action, detail, created_at FROM promo_activity WHERE promotion_id = $1 ORDER BY created_at DESC LIMIT 50",
            promotion_id,
        )
    return {
        "activity": [
            {"actor": r["actor"], "action": r["action"], "detail": r["detail"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ],
        "db_available": True,
    }


@router.get("/planning/activity/recent")
async def recent_activity():
    """Recent write-back activity across all promotions (for a dashboard feed)."""
    await _ensure_tables()
    pool = await db.get_pool()
    if not pool:
        return {"activity": [], "db_available": False}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT promotion_id, actor, action, detail, created_at FROM promo_activity ORDER BY created_at DESC LIMIT 30"
        )
    return {
        "activity": [
            {"promotion_id": r["promotion_id"], "actor": r["actor"], "action": r["action"],
             "detail": r["detail"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ],
        "db_available": True,
    }

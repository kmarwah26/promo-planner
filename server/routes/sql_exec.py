"""Shared helper for running SQL against a Databricks SQL warehouse over REST.

Uses the same OBO/service-principal auth as the rest of the app (see server/config.py)
and returns rows as a list of dicts keyed by column name.
"""
import os
import httpx
from fastapi import HTTPException, Request
from server.config import get_workspace_host, get_auth_headers, get_workspace_client

# Warehouse used for all Unity Catalog reads. Overridable via env for other workspaces.
DEFAULT_WAREHOUSE_ID = os.environ.get("PROMO_WAREHOUSE_ID", "efe860484f99f5a3")

# Fully-qualified schema holding the RGM demo data.
PROMO_CATALOG = os.environ.get("PROMO_CATALOG", "serverless_razks1_catalog")
PROMO_SCHEMA = os.environ.get("PROMO_SCHEMA", "promo_planning")
FQ = f"{PROMO_CATALOG}.{PROMO_SCHEMA}"

_cached_wh: str | None = None


def _resolve_warehouse(request: Request | None) -> str:
    """Return a usable warehouse id: env override, else the first available one."""
    global _cached_wh
    if DEFAULT_WAREHOUSE_ID:
        return DEFAULT_WAREHOUSE_ID
    if _cached_wh:
        return _cached_wh
    try:
        w = get_workspace_client(request)
        for wh in w.warehouses.list():
            _cached_wh = wh.id
            return wh.id
    except Exception:
        pass
    return ""


async def run_query(request: Request | None, sql: str, warehouse_id: str | None = None) -> list[dict]:
    """Execute a SQL statement and return rows as list[dict]. Raises HTTPException on error."""
    host = get_workspace_host().rstrip("/")
    headers = get_auth_headers(request)
    wid = warehouse_id or _resolve_warehouse(request)
    if not wid:
        raise HTTPException(status_code=503, detail="No SQL warehouse available")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{host}/api/2.0/sql/statements",
                headers=headers,
                json={"warehouse_id": wid, "statement": sql, "wait_timeout": "50s"},
            )
            resp.raise_for_status()
            data = resp.json()
            stmt_id = data.get("statement_id", "")
            state = data.get("status", {}).get("state", "")
            import asyncio
            while state in ("PENDING", "RUNNING") and stmt_id:
                await asyncio.sleep(1.5)
                poll = await client.get(f"{host}/api/2.0/sql/statements/{stmt_id}", headers=headers)
                poll.raise_for_status()
                data = poll.json()
                state = data.get("status", {}).get("state", "")
            if state != "SUCCEEDED":
                err = data.get("status", {}).get("error", {}).get("message", "unknown error")
                raise HTTPException(status_code=500, detail=f"Query failed: {err}")
            manifest = data.get("manifest", {})
            cols = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
            rows = data.get("result", {}).get("data_array", []) or []
            return [dict(zip(cols, r)) for r in rows]
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)

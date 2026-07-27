import os
from fastapi import APIRouter, HTTPException, Request
from server.config import get_workspace_client, get_workspace_host, IS_DATABRICKS_APP
from server.db import db

router = APIRouter(tags=["user"])


@router.get("/me")
async def get_current_user(request: Request):
    try:
        if IS_DATABRICKS_APP:
            # Databricks Apps injects the logged-in user's identity via headers
            email = request.headers.get("X-Forwarded-Email", "")
            preferred = request.headers.get("X-Forwarded-Preferred-Username", "")
            user_name = email or preferred
            # Derive display name from email (e.g. "jane.doe@company.com" -> "Jane Doe")
            display_name = user_name
            if email and "@" in email:
                local = email.split("@")[0]
                display_name = " ".join(part.capitalize() for part in local.replace(".", " ").replace("_", " ").split())
            return {
                # Per-user identity key (used for per-user chat history). Prefer the
                # stable X-Forwarded-User id, but fall back to the email/username —
                # X-Forwarded-User can be empty, and an empty id would collapse every
                # user's history into one shared bucket per room.
                "id": request.headers.get("X-Forwarded-User", "") or user_name,
                "user_name": user_name,
                "display_name": display_name,
            }
        else:
            w = get_workspace_client()
            me = w.current_user.me()
            return {
                "id": str(me.id) if me.id else "",
                "user_name": me.user_name or "",
                "display_name": me.display_name or "",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logout-url")
async def get_logout_url():
    """Workspace sign-out URL used to force a fresh SSO session (and OBO token re-mint).

    A plain page reload reuses the already-minted forwarded token, so it can't pick up
    OAuth scopes added after the user last consented. Sending the user through the
    workspace logout clears the Databricks session; on their next visit the Apps proxy
    re-mints the token against the app's *current* scopes — which is what clears an OBO
    403 after scopes change. The app can't clear the Databricks-domain cookie itself
    (different origin), so the frontend navigates the top-level window here.
    """
    host = get_workspace_host().rstrip("/")
    # /login.html?logout=true is the workspace sign-out entry point; after logout the
    # user lands on the sign-in page and re-authenticates (re-consenting to new scopes).
    return {"logout_url": f"{host}/login.html?logout=true" if host else ""}


@router.get("/services")
async def get_services():
    """Report all connected services and their status."""
    services = []
    host = get_workspace_host()

    # 1. Databricks Workspace
    try:
        w = get_workspace_client()
        me = w.current_user.me()
        services.append({
            "name": "Databricks Workspace",
            "type": "workspace",
            "status": "connected",
            "details": {
                "host": host,
                "user": me.user_name or "",
                "display_name": me.display_name or "",
                "auth_mode": "service_principal" if IS_DATABRICKS_APP else "profile",
            },
        })
    except Exception as e:
        services.append({
            "name": "Databricks Workspace",
            "type": "workspace",
            "status": "error",
            "error": str(e),
        })

    # 2. Unity Catalog
    try:
        w = get_workspace_client()
        cat_count = sum(1 for _ in w.catalogs.list())
        services.append({
            "name": "Unity Catalog",
            "type": "catalog",
            "status": "connected",
            "details": {"catalogs": cat_count},
        })
    except Exception as e:
        services.append({
            "name": "Unity Catalog",
            "type": "catalog",
            "status": "error",
            "error": str(e),
        })

    # 3. SQL Warehouses
    try:
        w = get_workspace_client()
        wh_list = list(w.warehouses.list())
        running = sum(1 for wh in wh_list if str(wh.state).upper().find("RUNNING") >= 0)
        services.append({
            "name": "SQL Warehouses",
            "type": "warehouse",
            "status": "connected",
            "details": {"total": len(wh_list), "running": running},
        })
    except Exception as e:
        services.append({
            "name": "SQL Warehouses",
            "type": "warehouse",
            "status": "error",
            "error": str(e),
        })

    # 4. Genie Rooms (via API)
    try:
        import httpx
        from server.config import get_auth_headers
        headers = get_auth_headers()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{host}/api/2.0/genie/spaces", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            spaces = data.get("spaces", data.get("genie_spaces", []))
            services.append({
                "name": "Genie Rooms",
                "type": "genie",
                "status": "connected",
                "details": {"rooms": len(spaces)},
            })
    except Exception as e:
        services.append({
            "name": "Genie Rooms",
            "type": "genie",
            "status": "error",
            "error": str(e),
        })

    # 5. Lakebase Cache
    try:
        pool = await db.get_pool()
        if pool:
            # Verify connection is alive with a simple query
            await pool.fetchrow("SELECT 1")
            # Try to get cache stats, but don't fail if tables don't exist yet
            details = {
                "host": os.environ.get("PGHOST", ""),
                "database": os.environ.get("PGDATABASE", ""),
            }
            try:
                row = await pool.fetchrow(
                    "SELECT "
                    "(SELECT count(*) FROM genie_rooms) as rooms, "
                    "(SELECT count(*) FROM catalog_tables) as tables"
                )
                if row:
                    details["cached_rooms"] = row["rooms"]
                    details["cached_tables"] = row["tables"]
            except Exception:
                details["cache_tables"] = "not initialized (run Setup)"
            services.append({
                "name": "Lakebase Cache",
                "type": "database",
                "status": "connected",
                "details": details,
            })
        else:
            services.append({
                "name": "Lakebase Cache",
                "type": "database",
                "status": "unavailable",
                "details": {"reason": "No database connection configured"},
            })
    except Exception as e:
        services.append({
            "name": "Lakebase Cache",
            "type": "database",
            "status": "error",
            "error": str(e),
        })

    # 6. Foundation Model API
    try:
        import httpx
        from server.config import get_auth_headers
        headers = get_auth_headers()
        async with httpx.AsyncClient(timeout=10) as client:
            # List serving endpoints to verify access
            resp = await client.get(f"{host}/api/2.0/serving-endpoints", headers=headers)
            resp.raise_for_status()
            endpoints = resp.json().get("endpoints", [])
            fm_endpoints = [
                e["name"] for e in endpoints
                if e.get("name", "").startswith("databricks-") and e.get("state", {}).get("ready") == "READY"
            ]
            services.append({
                "name": "Foundation Model API",
                "type": "llm",
                "status": "connected",
                "details": {
                    "endpoint": f"{host}/serving-endpoints",
                    "total_endpoints": len(endpoints),
                    "models": fm_endpoints[:8],
                },
            })
    except Exception as e:
        services.append({
            "name": "Foundation Model API",
            "type": "llm",
            "status": "error",
            "error": str(e),
        })

    return {"services": services}

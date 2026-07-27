from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from server.routes import catalog, genie, warehouses, user, promos, planning

app = FastAPI(title="Promotion Planning Genie Agents")

app.include_router(catalog.router, prefix="/api")
app.include_router(genie.router, prefix="/api")
app.include_router(warehouses.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(promos.router, prefix="/api")
app.include_router(planning.router, prefix="/api")


@app.get("/api/db-health")
async def db_health():
    """Diagnostic endpoint for Lakebase connectivity."""
    from server.db import db
    from server.db import _get_user, _get_token
    info = {
        "PGHOST": os.environ.get("PGHOST", ""),
        "PGPORT": os.environ.get("PGPORT", ""),
        "PGDATABASE": os.environ.get("PGDATABASE", ""),
        "PGUSER_resolved": _get_user(),
        "token_available": bool(_get_token()),
        "pool_exists": db._pool is not None,
    }
    try:
        pool = await db.get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            info["status"] = "connected"
        else:
            info["status"] = "no_pool"
    except Exception as e:
        info["status"] = f"error: {e}"
    return info


# Serve React frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dir):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(frontend_dir, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))

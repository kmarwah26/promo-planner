from fastapi import APIRouter, HTTPException, Request
from databricks.sdk.errors import PermissionDenied, Unauthenticated
from server.config import get_workspace_client, OBO_REAUTH_MESSAGE

router = APIRouter(tags=["warehouses"])


@router.get("/warehouses")
async def list_warehouses(request: Request):
    try:
        w = get_workspace_client(request)
        warehouses = []
        for wh in w.warehouses.list():
            warehouses.append({
                "id": wh.id,
                "name": wh.name,
                "state": str(wh.state) if wh.state else "",
                "cluster_size": wh.cluster_size or "",
            })
        return {"warehouses": warehouses}
    except (PermissionDenied, Unauthenticated):
        raise HTTPException(status_code=403, detail=OBO_REAUTH_MESSAGE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/warehouses/{warehouse_id}/start")
async def start_warehouse(warehouse_id: str, request: Request):
    try:
        w = get_workspace_client(request)
        w.warehouses.start(warehouse_id)
        return {"started": True, "warehouse_id": warehouse_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

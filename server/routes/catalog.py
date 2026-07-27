import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from server.config import get_workspace_host, get_auth_headers
from server.db import db

router = APIRouter(tags=["catalog"])


async def _uc_list(request: Request, path: str, params: dict, key: str) -> list:
    """List a Unity Catalog collection over REST, following pagination.

    We use REST instead of the SDK because the pinned databricks-sdk (0.67.0) can fail to
    parse responses when include_browse surfaces browse-only objects with sparse fields
    (it 500'd on /schemas). The UC list APIs paginate — catalogs/schemas/tables return a
    `next_page_token` and only a partial page even with a large max_results — so we must
    follow the token or we silently drop everything past page one (symptom: a catalog the
    user has access to is missing from the list). Mirrors the httpx pattern in genie.py.
    """
    host = get_workspace_host().rstrip("/")
    headers = get_auth_headers(request)
    items: list = []
    page_token = None
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(50):  # safety cap: 50 pages
            q = dict(params)
            if page_token:
                q["page_token"] = page_token
            resp = await client.get(f"{host}{path}", headers=headers, params=q)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get(key, []) or [])
            page_token = data.get("next_page_token")
            if not page_token:
                break
    return items


@router.get("/catalog-search")
async def search_catalog(request: Request, q: str = Query(..., min_length=1)):
    """Search by three-level namespace or plain table name."""
    try:
        parts = [p.strip() for p in q.split(".")]
        results = []

        if len(parts) == 1:
            prefix = parts[0].lower()

            # Try cached table search first (fast)
            try:
                pool = await db.get_pool()
                if pool and len(prefix) >= 2:
                    rows = await pool.fetch(
                        "SELECT full_name, table_name, catalog_name, schema_name, table_type, comment "
                        "FROM catalog_tables "
                        "WHERE table_name ILIKE $1 OR full_name ILIKE $1 OR comment ILIKE $1 "
                        "ORDER BY table_name LIMIT 50",
                        f"%{prefix}%",
                    )
                    for r in rows:
                        results.append({
                            "type": "table",
                            "name": r["table_name"],
                            "full_name": r["full_name"],
                            "catalog": r["catalog_name"],
                            "schema": r["schema_name"],
                            "table_type": r["table_type"] or "",
                            "comment": r["comment"] or "",
                        })
                    if results:
                        return {"results": results, "query": q}
            except Exception:
                pass

            # Fallback: filter catalogs by name
            try:
                raw = await _uc_list(request, "/api/2.1/unity-catalog/catalogs",
                                     {"include_browse": "true", "max_results": 500}, "catalogs")
                for c in raw:
                    if c.get("name") and prefix in c["name"].lower():
                        results.append({"type": "catalog", "name": c["name"], "full_name": c["name"]})
                    if len(results) >= 50:
                        break
            except Exception:
                pass

        elif len(parts) == 2:
            # catalog.schema — list matching schemas
            catalog, schema_prefix = parts[0], parts[1].lower()
            try:
                raw = await _uc_list(request, "/api/2.1/unity-catalog/schemas",
                                     {"catalog_name": catalog, "include_browse": "true", "max_results": 500}, "schemas")
                for s in raw:
                    if s.get("name") and schema_prefix in s["name"].lower():
                        results.append({
                            "type": "schema",
                            "name": s["name"],
                            "full_name": s.get("full_name", ""),
                            "catalog": catalog,
                        })
                    if len(results) >= 50:
                        break
            except Exception:
                pass

        elif len(parts) >= 3:
            # catalog.schema.table — list matching tables
            catalog, schema, table_prefix = parts[0], parts[1], ".".join(parts[2:]).lower()
            try:
                raw = await _uc_list(request, "/api/2.1/unity-catalog/tables",
                                     {"catalog_name": catalog, "schema_name": schema, "include_browse": "true", "max_results": 200}, "tables")
                for t in raw:
                    if t.get("name") and table_prefix in t["name"].lower():
                        results.append({
                            "type": "table",
                            "name": t["name"],
                            "full_name": t.get("full_name", ""),
                            "catalog": catalog,
                            "schema": schema,
                            "table_type": t.get("table_type", ""),
                            "comment": t.get("comment", ""),
                            "columns": [
                                {
                                    "name": col.get("name", ""),
                                    "type": col.get("type_text", ""),
                                    "comment": col.get("comment", ""),
                                }
                                for col in (t.get("columns") or [])
                            ],
                        })
                    if len(results) >= 50:
                        break
            except Exception:
                pass

        return {"results": results, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalogs")
async def list_catalogs(request: Request):
    try:
        raw = await _uc_list(
            request, "/api/2.1/unity-catalog/catalogs",
            {"include_browse": "true", "max_results": 500}, "catalogs",
        )
        catalogs = [
            {"name": c.get("name", ""), "comment": c.get("comment", ""), "owner": c.get("owner", "")}
            for c in raw if c.get("name")
        ]
        catalogs.sort(key=lambda x: x["name"].lower())
        return {"catalogs": catalogs}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalogs/{catalog_name}/schemas")
async def list_schemas(catalog_name: str, request: Request):
    try:
        # include_browse surfaces schemas the user has only browse/metadata access to
        # (not just ones they can fully query) — matches Catalog Explorer.
        raw = await _uc_list(
            request, "/api/2.1/unity-catalog/schemas",
            {"catalog_name": catalog_name, "include_browse": "true", "max_results": 500}, "schemas",
        )
        schemas = [
            {"name": s.get("name", ""), "full_name": s.get("full_name", ""), "comment": s.get("comment", "")}
            for s in raw if s.get("name")
        ]
        return {"schemas": schemas}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalogs/{catalog_name}/schemas/{schema_name}/tables")
async def list_tables(catalog_name: str, schema_name: str, request: Request):
    try:
        # include_browse is essential under OBO: without it, tables the user has only
        # browse/metadata access to (no SELECT grant yet) are silently omitted, so a
        # schema appears to have no tables. Matches Catalog Explorer.
        raw = await _uc_list(
            request, "/api/2.1/unity-catalog/tables",
            {"catalog_name": catalog_name, "schema_name": schema_name, "include_browse": "true", "max_results": 200}, "tables",
        )
        tables = []
        for t in raw:
            if not t.get("name"):
                continue
            tables.append({
                "name": t.get("name", ""),
                "full_name": t.get("full_name", ""),
                "table_type": t.get("table_type", ""),
                "comment": t.get("comment", ""),
                "columns": [
                    {
                        "name": col.get("name", ""),
                        "type": col.get("type_text", ""),
                        "comment": col.get("comment", ""),
                    }
                    for col in (t.get("columns") or [])
                ],
            })
        return {"tables": tables}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

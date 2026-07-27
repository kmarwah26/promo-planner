import json
import asyncio
import uuid
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from server.config import get_workspace_host, get_auth_headers, OBO_REAUTH_MESSAGE

router = APIRouter(tags=["genie"])

API_PREFIX = "/api/2.0/genie/spaces"


def _client(request: Request | None = None) -> tuple[str, dict]:
    host = get_workspace_host()
    headers = get_auth_headers(request)
    return host, headers


class CreateRoomRequest(BaseModel):
    title: str
    description: str
    table_identifiers: list[str]
    warehouse_id: str | None = None
    sample_queries: list[dict] | None = None  # [{question, sql}]
    instructions: str | None = None


class UpdateRoomRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    table_identifiers: list[str] | None = None
    warehouse_id: str | None = None
    sample_queries: list[dict] | None = None
    instructions: str | None = None


class SendMessageRequest(BaseModel):
    content: str


# ── Helpers ──


def _build_serialized_space(
    table_identifiers: list[str],
    instructions: str | None = None,
    sample_queries: list[dict] | None = None,
) -> str:
    """Build serialized_space JSON with tables, text instructions, and example queries."""
    space_config: dict = {
        "version": 2,
        "data_sources": {
            "tables": [{"identifier": t} for t in sorted(table_identifiers)],
        },
    }

    instr_block: dict = {}

    # Text instructions — single item, content is an array of strings
    if instructions and instructions.strip():
        instr_block["text_instructions"] = [
            {"id": uuid.uuid4().hex, "content": [instructions.strip()]}
        ]

    # Example question SQLs — each needs id, question (array), sql (array), sorted by id
    if sample_queries:
        eq_items = []
        for sq in sample_queries:
            q = sq.get("question", "").strip() if sq.get("question") else ""
            s = sq.get("sql", "").strip() if sq.get("sql") else ""
            if q or s:
                eq_items.append({
                    "id": uuid.uuid4().hex,
                    "question": [q] if q else [],
                    "sql": [s] if s else [],
                })
        # API requires items sorted by id
        eq_items.sort(key=lambda x: x["id"])
        if eq_items:
            instr_block["example_question_sqls"] = eq_items

    if instr_block:
        space_config["instructions"] = instr_block

    return json.dumps(space_config)


def _parse_room_detail(data: dict) -> dict:
    """Parse a room response, extracting tables, instructions, and example queries from serialized_space."""
    result = {
        "space_id": data.get("space_id", data.get("id", "")),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "warehouse_id": data.get("warehouse_id", ""),
        "parent_path": data.get("parent_path", ""),
        "table_identifiers": [],
        "instructions": "",
        "sample_queries": [],
    }
    ss = data.get("serialized_space", "")
    if ss:
        try:
            space = json.loads(ss)
            tables = space.get("data_sources", {}).get("tables", [])
            result["table_identifiers"] = [
                t.get("identifier", "") for t in tables if t.get("identifier")
            ]
            # Extract instructions
            instr = space.get("instructions", {})
            text_items = instr.get("text_instructions", [])
            if text_items:
                # Single item with content array
                content = text_items[0].get("content", [])
                result["instructions"] = "\n".join(content) if content else ""

            # Extract example queries
            eq_items = instr.get("example_question_sqls", [])
            for eq in eq_items:
                questions = eq.get("question", [])
                sqls = eq.get("sql", [])
                result["sample_queries"].append({
                    "question": questions[0] if questions else "",
                    "sql": sqls[0] if sqls else "",
                })
        except (json.JSONDecodeError, TypeError):
            pass
    return result


# ── List Genie Rooms ──


@router.get("/genie/rooms")
async def list_genie_rooms(request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{host}{API_PREFIX}", headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            spaces = data.get("spaces", data.get("genie_spaces", []))
            rooms = []
            for s in spaces:
                rooms.append({
                    "id": s.get("space_id", s.get("id", "")),
                    "title": s.get("title", s.get("name", "Untitled")),
                    "description": s.get("description", ""),
                    "creator_id": s.get("creator_id", ""),
                    "creator_name": s.get("creator_name", ""),
                })
            return {"rooms": rooms}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise HTTPException(status_code=403, detail=OBO_REAUTH_MESSAGE)
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Create Genie Room ──


@router.post("/genie/rooms")
async def create_genie_room(req: CreateRoomRequest, request: Request):
    host, headers = _client(request)

    serialized_space = _build_serialized_space(
        table_identifiers=req.table_identifiers,
        instructions=req.instructions,
        sample_queries=req.sample_queries,
    )

    body: dict = {
        "title": req.title,
        "description": req.description.strip() if req.description else req.title,
        "serialized_space": serialized_space,
    }

    # Ensure a warehouse is always provided — auto-select if not specified
    wh_id = req.warehouse_id
    if not wh_id:
        try:
            from server.config import get_workspace_client
            wc = get_workspace_client(request)
            for wh in wc.warehouses.list():
                state = str(wh.state) if wh.state else ""
                if "RUNNING" in state or "STARTING" in state:
                    wh_id = wh.id
                    break
                if not wh_id and wh.id:
                    wh_id = wh.id  # fallback to any warehouse
        except Exception:
            pass
    if wh_id:
        body["warehouse_id"] = wh_id
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{host}{API_PREFIX}",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get Genie Room Detail ──


@router.get("/genie/rooms/{room_id}")
async def get_genie_room(room_id: str, request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{host}{API_PREFIX}/{room_id}",
                headers=headers,
                params={"include_serialized_space": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
            return _parse_room_detail(data)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Update Genie Room ──


@router.patch("/genie/rooms/{room_id}")
async def update_genie_room(room_id: str, req: UpdateRoomRequest, request: Request):
    host, headers = _client(request)
    body: dict = {}

    if req.title is not None:
        body["title"] = req.title

    if req.description is not None:
        body["description"] = req.description.strip() if req.description else ""

    # Build serialized_space if tables, instructions, or queries changed
    needs_space_update = (
        req.table_identifiers is not None
        or req.instructions is not None
        or req.sample_queries is not None
    )
    if needs_space_update:
        # We need the current state for fields that weren't provided
        # Fetch existing room to merge
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                existing_resp = await client.get(
                    f"{host}{API_PREFIX}/{room_id}",
                    headers=headers,
                    params={"include_serialized_space": "true"},
                )
                existing_resp.raise_for_status()
                existing = _parse_room_detail(existing_resp.json())
        except Exception:
            existing = {"table_identifiers": [], "instructions": "", "sample_queries": []}

        tables = req.table_identifiers if req.table_identifiers is not None else existing.get("table_identifiers", [])
        instructions = req.instructions if req.instructions is not None else existing.get("instructions", "")
        queries = req.sample_queries if req.sample_queries is not None else existing.get("sample_queries", [])

        body["serialized_space"] = _build_serialized_space(
            table_identifiers=tables,
            instructions=instructions or None,
            sample_queries=queries or None,
        )

    if req.warehouse_id is not None:
        body["warehouse_id"] = req.warehouse_id

    if not body:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{host}{API_PREFIX}/{room_id}",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return _parse_room_detail(data)
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete Genie Room ──


@router.delete("/genie/rooms/{room_id}")
async def delete_genie_room(room_id: str, request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{host}{API_PREFIX}/{room_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return {"deleted": True}
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Execute SQL directly ──


class ExecuteSqlRequest(BaseModel):
    warehouse_id: str
    statement: str


@router.post("/execute-sql")
async def execute_sql(req: ExecuteSqlRequest, request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{host}/api/2.0/sql/statements",
                headers=headers,
                json={
                    "warehouse_id": req.warehouse_id,
                    "statement": req.statement,
                    "wait_timeout": "30s",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", {}).get("state", "")
            # If pending, poll until done
            stmt_id = data.get("statement_id", "")
            if status == "PENDING" and stmt_id:
                import asyncio
                for _ in range(30):
                    await asyncio.sleep(2)
                    poll_resp = await client.get(
                        f"{host}/api/2.0/sql/statements/{stmt_id}",
                        headers=headers,
                    )
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        status = data.get("status", {}).get("state", "")
                        if status in ("SUCCEEDED", "FAILED", "CANCELED", "CLOSED"):
                            break
            return data
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Start Conversation ──


@router.post("/genie/rooms/{room_id}/conversations")
async def start_conversation(room_id: str, req: SendMessageRequest, request: Request):
    host, headers = _client(request)
    content = req.content
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{host}{API_PREFIX}/{room_id}/start-conversation",
                headers=headers,
                json={"content": content},
            )
            resp.raise_for_status()
            data = resp.json()
            conversation_id = data.get("conversation_id", "")
            message_id = data.get("message_id", "")
            # Poll for result
            result = await _poll_message(
                client, host, headers, room_id, conversation_id, message_id
            )
            return {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "result": result,
            }
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Send Message in Conversation ──


@router.post("/genie/rooms/{room_id}/conversations/{conversation_id}/messages")
async def send_message(room_id: str, conversation_id: str, req: SendMessageRequest, request: Request):
    host, headers = _client(request)
    content = req.content
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{host}{API_PREFIX}/{room_id}/conversations/{conversation_id}/messages",
                headers=headers,
                json={"content": content},
            )
            resp.raise_for_status()
            data = resp.json()
            message_id = data.get("id", data.get("message_id", ""))
            # Poll for result
            result = await _poll_message(
                client, host, headers, room_id, conversation_id, message_id
            )
            return {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "result": result,
            }
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get Message Result ──


@router.get(
    "/genie/rooms/{room_id}/conversations/{conversation_id}/messages/{message_id}"
)
async def get_message(room_id: str, conversation_id: str, message_id: str, request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{host}{API_PREFIX}/{room_id}/conversations/{conversation_id}/messages/{message_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get Query Result ──


@router.get(
    "/genie/rooms/{room_id}/conversations/{conversation_id}/messages/{message_id}/query-result"
)
async def get_query_result(room_id: str, conversation_id: str, message_id: str, request: Request):
    host, headers = _client(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{host}{API_PREFIX}/{room_id}/conversations/{conversation_id}/messages/{message_id}/query-result",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Poll Helper ──


async def _poll_message(
    client: httpx.AsyncClient,
    host: str,
    headers: dict,
    room_id: str,
    conversation_id: str,
    message_id: str,
    max_attempts: int = 30,
    interval: float = 2.0,
) -> dict:
    url = f"{host}{API_PREFIX}/{room_id}/conversations/{conversation_id}/messages/{message_id}"
    for _ in range(max_attempts):
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "")
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                # Try to get query result if available
                attachments = data.get("attachments", [])
                query_attachment = None
                for att in attachments:
                    if att.get("query", {}).get("query"):
                        query_attachment = att
                        break
                result = {
                    "status": status,
                    "message": data,
                    "query": query_attachment.get("query", {}).get("query", "") if query_attachment else "",
                    "description": query_attachment.get("query", {}).get("description", "") if query_attachment else "",
                }
                # Fetch query result data if we have a query attachment
                if query_attachment:
                    try:
                        qr_resp = await client.get(f"{url}/query-result", headers=headers)
                        if qr_resp.status_code == 200:
                            qr_data = qr_resp.json()
                            # Genie wraps in statement_response; normalize to
                            # {manifest, result{data_array}} matching SQL Statement API shape
                            sr = qr_data.get("statement_response") or qr_data
                            manifest = sr.get("manifest", {})
                            raw_result = sr.get("result", {})

                            # Convert data_typed_array → data_array
                            data_array = raw_result.get("data_array")
                            if not data_array:
                                typed = raw_result.get("data_typed_array", [])
                                if typed:
                                    data_array = []
                                    for row in typed:
                                        vals = row.get("values", [])
                                        data_array.append([v.get("str") for v in vals])

                            result["query_result"] = {
                                "manifest": manifest,
                                "result": {"data_array": data_array or []},
                            }
                        else:
                            print(f"[genie] query-result status: {qr_resp.status_code}")
                    except Exception as e:
                        print(f"[genie] query-result fetch error: {e}")
                # Get text content
                text_attachment = None
                for att in attachments:
                    if att.get("text", {}).get("content"):
                        text_attachment = att
                        break
                if text_attachment:
                    result["text"] = text_attachment["text"]["content"]
                return result
        await asyncio.sleep(interval)
    return {"status": "TIMEOUT", "message": "Polling timed out"}

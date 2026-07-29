"""Genie chat over the Promo 1YP pricing data.

Exposes a small API for the floating "Ask the data" widget:
  * GET  /genie/space          — resolve (find-or-create + cache) the Genie space
  * POST /genie/conversations  — start a conversation (asks the first question)
  * POST /genie/conversations/{cid}/messages — follow-up in the same thread

The space is created over the governed pricing tables with a few sample questions
and light instructions, so it self-heals on a fresh workspace / redeploy.
"""
import os
import json
import uuid
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from server.config import get_workspace_host, get_auth_headers, get_workspace_client, OBO_REAUTH_MESSAGE
from server.routes.sql_exec import FQ, DEFAULT_WAREHOUSE_ID

router = APIRouter(tags=["genie"])

API_PREFIX = "/api/2.0/genie/spaces"

SPACE_TITLE = "Promo 1YP — Pricing Genie"
SPACE_DESC = "Ask questions about wholesale promo pricing: REC PPTR, discounts, promo weeks, by wholesaler / brand / PRC group."

INSTRUCTIONS = (
    "This space covers wholesale promotional pricing. Grain: one line is "
    "(plan_year, wholesaler, brand, PRC group); fact_promo_week holds per-ISO-week "
    "promo overrides. Discounts (incremental_discount, absolute_discount) are DOLLARS "
    "off per case; rec_pptr is the recommended price to retailer (base_pptr minus the "
    "discount). approval_status is committed (2026), pending, or approved (2027 Final "
    "Plan). Prefer plan_year = 2027 unless asked otherwise. Join fact_promo_week to "
    "fact_price_plan on (plan_year, wholesaler_id, brand_code, prc_code) for base_pptr "
    "and metadata."
)

SAMPLE_QUERIES = [
    {"question": "How many promo weeks are planned for 2027 by brand?",
     "sql": f"SELECT brand_code, count(*) AS promo_weeks FROM {FQ}.fact_promo_week "
            f"WHERE plan_year = 2027 GROUP BY brand_code ORDER BY promo_weeks DESC"},
    {"question": "What is the total discount dollars for 2027 by wholesaler?",
     "sql": f"SELECT pw.wholesaler_id, round(sum(p.base_pptr - pw.rec_pptr), 2) AS total_discount "
            f"FROM {FQ}.fact_promo_week pw JOIN {FQ}.fact_price_plan p "
            f"ON p.plan_year = pw.plan_year AND p.wholesaler_id = pw.wholesaler_id "
            f"AND p.brand_code = pw.brand_code AND p.prc_code = pw.prc_code "
            f"WHERE pw.plan_year = 2027 GROUP BY pw.wholesaler_id ORDER BY total_discount DESC LIMIT 20"},
    {"question": "Which brands have the deepest average discount in 2027?",
     "sql": f"SELECT brand_code, round(avg(incremental_discount), 2) AS avg_discount "
            f"FROM {FQ}.fact_promo_week WHERE plan_year = 2027 AND incremental_discount IS NOT NULL "
            f"GROUP BY brand_code ORDER BY avg_discount DESC"},
]

SUGGESTIONS = [
    "How many promo weeks are planned for 2027 by brand?",
    "What is the total discount dollars for 2027 by wholesaler?",
    "Which brands have the deepest average discount in 2027?",
    "How many lines are on promotion vs total for 2027?",
]

# Tables the space can reason over.
TABLES = [f"{FQ}.fact_promo_week", f"{FQ}.fact_price_plan",
          f"{FQ}.dim_wholesaler", f"{FQ}.dim_brand", f"{FQ}.dim_prc_group", f"{FQ}.dim_iso_week"]

# Cache the resolved space id for the process lifetime.
_space_id: str | None = None


def _client(request: Request | None = None) -> tuple[str, dict]:
    return get_workspace_host(), get_auth_headers(request)


def _serialized_space() -> str:
    eq = sorted(
        ({"id": uuid.uuid4().hex, "question": [q["question"]], "sql": [q["sql"]]}
         for q in SAMPLE_QUERIES),
        key=lambda x: x["id"],
    )
    return json.dumps({
        "version": 2,
        "data_sources": {"tables": [{"identifier": t} for t in sorted(TABLES)]},
        "instructions": {
            "text_instructions": [{"id": uuid.uuid4().hex, "content": [INSTRUCTIONS]}],
            "example_question_sqls": eq,
        },
    })


def _warehouse(request) -> str:
    if DEFAULT_WAREHOUSE_ID:
        return DEFAULT_WAREHOUSE_ID
    try:
        for wh in get_workspace_client(request).warehouses.list():
            if wh.id:
                return wh.id
    except Exception:
        pass
    return ""


async def _find_existing(client, host, headers) -> str | None:
    """Return the id of an existing Promo 1YP space, if one is accessible."""
    try:
        resp = await client.get(f"{host}{API_PREFIX}", headers=headers, params={"page_size": 100})
        if resp.status_code == 200:
            for sp in resp.json().get("spaces", []):
                if sp.get("title") == SPACE_TITLE:
                    return sp.get("space_id") or sp.get("id")
    except Exception:
        pass
    return None


class ResolveRequest(BaseModel):
    force_create: bool = False


@router.get("/genie/space")
async def resolve_space(request: Request):
    """Find-or-create the pricing Genie space; cached for the process lifetime."""
    global _space_id
    if _space_id:
        return {"space_id": _space_id, "title": SPACE_TITLE, "suggestions": SUGGESTIONS, "created": False}
    host, headers = _client(request)
    async with httpx.AsyncClient(timeout=60) as client:
        existing = await _find_existing(client, host, headers)
        if existing:
            _space_id = existing
            return {"space_id": _space_id, "title": SPACE_TITLE, "suggestions": SUGGESTIONS, "created": False}
        # Create a fresh space over the pricing tables.
        body = {
            "title": SPACE_TITLE,
            "description": SPACE_DESC,
            "serialized_space": _serialized_space(),
        }
        wh = _warehouse(request)
        if wh:
            body["warehouse_id"] = wh
        try:
            resp = await client.post(f"{host}{API_PREFIX}", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            _space_id = data.get("space_id") or data.get("id")
            return {"space_id": _space_id, "title": SPACE_TITLE, "suggestions": SUGGESTIONS, "created": True}
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response else 500
            if code == 403:
                raise HTTPException(status_code=403, detail=OBO_REAUTH_MESSAGE)
            detail = e.response.text if e.response else str(e)
            raise HTTPException(status_code=code, detail=f"Could not create Genie space: {detail}")


class MessageRequest(BaseModel):
    content: str


@router.post("/genie/conversations")
async def start_conversation(req: MessageRequest, request: Request):
    global _space_id
    host, headers = _client(request)
    async with httpx.AsyncClient(timeout=90) as client:
        # Try the cached space; if it's gone/inaccessible for this (OBO) user, drop the
        # cache and re-resolve once as them, then retry.
        for attempt in range(2):
            space_id = await _require_space(request)
            resp = await client.post(
                f"{host}{API_PREFIX}/{space_id}/start-conversation",
                headers=headers, json={"content": req.content},
            )
            if resp.status_code == 404 and attempt == 0:
                _space_id = None
                continue
            break
        _raise(resp)
        data = resp.json()
        cid, mid = data.get("conversation_id", ""), data.get("message_id", "")
        result = await _poll_message(client, host, headers, space_id, cid, mid)
        return {"conversation_id": cid, "message_id": mid, "result": result}


@router.post("/genie/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, req: MessageRequest, request: Request):
    space_id = await _require_space(request)
    host, headers = _client(request)
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{host}{API_PREFIX}/{space_id}/conversations/{conversation_id}/messages",
            headers=headers, json={"content": req.content},
        )
        _raise(resp)
        data = resp.json()
        mid = data.get("id", data.get("message_id", ""))
        result = await _poll_message(client, host, headers, space_id, conversation_id, mid)
        return {"conversation_id": conversation_id, "message_id": mid, "result": result}


async def _require_space(request: Request) -> str:
    global _space_id
    if not _space_id:
        await resolve_space(request)
    if not _space_id:
        raise HTTPException(status_code=503, detail="Genie space unavailable")
    return _space_id


def _raise(resp):
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail=OBO_REAUTH_MESSAGE)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)


async def _poll_message(client, host, headers, space_id, conversation_id, message_id,
                        max_attempts: int = 45, interval: float = 2.0) -> dict:
    url = f"{host}{API_PREFIX}/{space_id}/conversations/{conversation_id}/messages/{message_id}"
    for _ in range(max_attempts):
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "")
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                attachments = data.get("attachments", [])
                q_att = next((a for a in attachments if a.get("query", {}).get("query")), None)
                text_att = next((a for a in attachments if a.get("text", {}).get("content")), None)
                result = {
                    "status": status,
                    "query": q_att.get("query", {}).get("query", "") if q_att else "",
                    "text": text_att["text"]["content"] if text_att else "",
                    "columns": [], "rows": [],
                }
                if q_att:
                    try:
                        qr = await client.get(f"{url}/query-result", headers=headers)
                        if qr.status_code == 200:
                            sr = qr.json().get("statement_response") or qr.json()
                            manifest = sr.get("manifest", {})
                            raw = sr.get("result", {})
                            cols = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
                            rows = raw.get("data_array")
                            if not rows:
                                rows = [[v.get("str") for v in r.get("values", [])]
                                        for r in raw.get("data_typed_array", [])]
                            result["columns"] = cols
                            result["rows"] = rows or []
                    except Exception as e:
                        print(f"[genie] query-result fetch error: {e}")
                return result
        await asyncio.sleep(interval)
    return {"status": "TIMEOUT", "text": "The request timed out. Please try again.", "query": "", "columns": [], "rows": []}

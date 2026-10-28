from __future__ import annotations

import json
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .wazzup import WazzupClient, WazzupError
from . import routing
import hashlib


class Settings(BaseSettings):
    app_mode: Literal["draft", "auto"] = "draft"
    webhook_secret: str = "change-me"
    database_path: str = "data/bot.db"
    knowledge_path: str = "knowledge/sales_book.json"
    match_threshold: float = 0.42
    routing_knowledge_path: str = "/var/lib/eva/knowledge/routing_release.json"
    public_base_url: str = ""
    wazzup_api_token: str = ""
    wazzup_webhook_token: str = "replace-with-long-random-string"
    wazzup_api_base: str = "https://api.wazzup24.com"
    wazzup_crm_forward_url: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / settings.database_path
KNOWLEDGE_PATH = BASE_DIR / settings.knowledge_path
# One pooled client: a new httpx client per webhook builds a fresh TLS context each time.
http_client = httpx.Client(timeout=15)

@asynccontextmanager
async def lifespan(_: FastAPI):
    knowledge = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    if settings.app_mode == "auto" and knowledge.get("production_enabled") is not True:
        raise RuntimeError("Knowledge release is not approved for automatic replies")
    init_db()
    yield
    http_client.close()


app = FastAPI(title="Sales chat assistant", version="0.1.0", lifespan=lifespan)


class InboundMessage(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    channel: Literal["vk", "max", "test"]
    chat_id: str = Field(min_length=1, max_length=200)
    sender_id: str = Field(min_length=1, max_length=200)
    branch_id: int | None = None
    customer_id: int | None = None
    source_channel_id: str | None = None
    chat_type: str | None = None
    text: str = Field(min_length=1, max_length=10_000)
    received_at: datetime | None = None
    has_attachment: bool = False


class ResolveTask(BaseModel):
    resolution: str = Field(min_length=1, max_length=2000)


class WazzupParty(BaseModel):
    chat_id: str | int | None = None
    chat_type: str | None = None
    name: str | None = None
    username: str | None = None
    phone: str | int | None = None


class WazzupMessage(BaseModel):
    message_id: str
    channel_id: str
    direction: str
    timestamp: int
    status: str | None = None
    text: str | None = None
    sender: WazzupParty | None = None
    has_attachment: bool = False
    recipient: WazzupParty


class WazzupWebhook(BaseModel):
    event: str
    data: list[WazzupMessage] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS routing_audit (
                inbound_id INTEGER PRIMARY KEY, trace_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversation_control (
                conversation_key TEXT PRIMARY KEY, state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbound_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                channel TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                branch_id INTEGER,
                customer_id INTEGER,
                source_channel_id TEXT,
                chat_type TEXT,
                text TEXT NOT NULL,
                received_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inbound_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                answer TEXT,
                knowledge_id TEXT,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(inbound_id) REFERENCES inbound_messages(id)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inbound_id INTEGER NOT NULL UNIQUE,
                branch_id INTEGER,
                priority INTEGER NOT NULL DEFAULT 2,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                due_at TEXT,
                resolution TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(inbound_id) REFERENCES inbound_messages(id)
            );
            """
        )


def require_secret(x_webhook_secret: str = Header(default="")) -> None:
    if not settings.webhook_secret or x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def wazzup_client() -> WazzupClient:
    return WazzupClient(settings.wazzup_api_token, settings.wazzup_api_base, http_client)


def normalize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[а-яёa-z0-9]+", text.lower())
        if len(token) > 2
    }


def load_knowledge() -> list[dict]:
    data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    return [item for item in data["entries"] if item.get("approved") is True
            or (settings.app_mode == "draft" and item.get("draft_review") is True)]


def score(message: str, entry: dict) -> float:
    query = normalize(message)
    if not query:
        return 0.0
    candidates = [entry.get("intent", ""), *entry.get("examples", [])]
    best = 0.0
    for candidate in candidates:
        words = normalize(candidate)
        if words:
            best = max(best, len(query & words) / len(query | words))
    return best


def find_answer(message: InboundMessage) -> tuple[dict | None, float]:
    ranked: list[tuple[float, dict]] = []
    for entry in load_knowledge():
        branch = entry.get("branch_id")
        if branch is not None and branch != message.branch_id:
            continue
        ranked.append((score(message.text, entry), entry))
    if not ranked:
        return None, 0.0
    confidence, entry = max(ranked, key=lambda pair: pair[0])
    return (entry if confidence >= settings.match_threshold else None), confidence


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": settings.app_mode}


@app.post("/webhooks/inbound", dependencies=[Depends(require_secret)])
def inbound(message: InboundMessage) -> dict:
    if settings.app_mode != 'draft':
        raise HTTPException(status_code=503, detail='Routing release supports draft only')
    received_at = (message.received_at or datetime.now(timezone.utc)).isoformat()
    conversation_key=hashlib.sha256(json.dumps([message.channel,message.source_channel_id,message.chat_type,message.chat_id,message.branch_id]).encode()).hexdigest()
    with db() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing=connection.execute('SELECT id FROM inbound_messages WHERE event_id=?',(message.event_id,)).fetchone()
        if existing:return {'status':'duplicate','inbound_id':existing['id']}
        cursor=connection.execute('INSERT INTO inbound_messages(event_id,channel,chat_id,sender_id,branch_id,customer_id,source_channel_id,chat_type,text,received_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (message.event_id,message.channel,message.chat_id,message.sender_id,message.branch_id,message.customer_id,message.source_channel_id,message.chat_type,message.text,received_at,utcnow()))
        inbound_id=cursor.lastrowid
        state=connection.execute('SELECT state FROM conversation_control WHERE conversation_key=?',(conversation_key,)).fetchone()
        previous=connection.execute('SELECT text FROM inbound_messages WHERE id<? AND channel=? AND chat_id=? AND source_channel_id IS ? AND chat_type IS ? AND branch_id IS ? ORDER BY id DESC LIMIT 1',
            (inbound_id,message.channel,message.chat_id,message.source_channel_id,message.chat_type,message.branch_id)).fetchone()
        try:
            release=routing.load(settings.routing_knowledge_path,settings.app_mode)
            result=routing.route(message.text,release,context={'previous_text':previous['text'] if previous else ''},attachment=message.has_attachment,human_active=bool(state and state['state'] in {'HUMAN_ACTIVE','HUMAN_REQUESTED'}))
            if state and state['state']=='HUMAN_REQUESTED' and result['reason_code']=='HUMAN_ACTIVE':result['reason_code']='HUMAN_HANDOFF_PENDING'
            result['knowledge_hash']=release['hash'];result['knowledge_version']=release['version'];result['row_warnings']=release['bad_rows']
        except routing.KnowledgeError as exc:
            result={'scenario':None,'reason_code':str(exc),'draft':None,'score':0,'sources':[],'version':routing.VERSION}
        if result['reason_code']=='EXPLICIT_HUMAN_REQUEST':
            connection.execute('INSERT OR REPLACE INTO conversation_control VALUES(?,?)',(conversation_key,'HUMAN_REQUESTED'))
        reason=result['reason_code'];answer=result.get('draft')
        category='technical_incident' if reason.startswith('KNOWLEDGE_') and reason!='KNOWLEDGE_GAP' else 'knowledge_gap' if reason=='KNOWLEDGE_GAP' else 'needs_action' if result.get('needs_action') or reason in {'HUMAN_ACTIVE','HUMAN_HANDOFF_PENDING'} else 'review_draft'
        status='draft' if answer else 'escalated'
        connection.execute('INSERT INTO replies(inbound_id,status,answer,knowledge_id,confidence,created_at) VALUES(?,?,?,?,?,?)',(inbound_id,status,answer,result.get('scenario'),result.get('score',0),utcnow()))
        task=connection.execute('INSERT INTO tasks(inbound_id,branch_id,priority,category,summary,created_at) VALUES(?,?,?,?,?,?)',(inbound_id,message.branch_id,3 if reason=='SAFETY_RISK' else 2,("review_draft" if category=="review_draft" else "needs_human"),message.text.strip()[:240],utcnow()))
        result.update(task_kind=category,stages={'normalization':'ok','direction':'inbound','client_identity':'unverified' if message.customer_id is None else 'provided_not_verified','context':'local_previous_inbound_only','knowledge':'error' if category=='technical_incident' else 'loaded','draft':'prepared' if answer else 'withheld','crm_action':'not_executed','notification':'pending_worker'},timestamp=utcnow())
        connection.execute('INSERT INTO routing_audit VALUES(?,?)',(inbound_id,json.dumps(result,ensure_ascii=False)))
        return {'status':status,'inbound_id':inbound_id,'task_id':task.lastrowid,'answer':answer,'knowledge_id':result.get('scenario'),'reason_code':reason,'confidence':round(result.get('score',0),3)}


@app.post("/webhooks/wazzup/{token}", response_model=None)
def wazzup_webhook(token: str, payload: dict, request: Request) -> Response | dict:
    if token != settings.wazzup_webhook_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    # Preserve the existing CRM integration's response, including contact/deal IDs.
    # Failure is not acknowledged: Wazzup can retry and inbound IDs deduplicate drafts.
    crm_response = None
    if settings.wazzup_crm_forward_url:
        forward_headers = {"Content-Type": "application/json"}
        authorization = request.headers.get("authorization")
        if authorization:
            forward_headers["Authorization"] = authorization
        try:
            crm_response = http_client.post(settings.wazzup_crm_forward_url, json=payload,
                                            headers=forward_headers, timeout=15)
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="CRM forwarding unavailable")
        if not crm_response.is_success:
            return Response(content=crm_response.content, status_code=crm_response.status_code,
                            media_type=crm_response.headers.get("content-type", "application/json"))
    result = process_wazzup_payload(payload)
    if crm_response is not None:
        return Response(content=crm_response.content, status_code=crm_response.status_code,
                        media_type=crm_response.headers.get("content-type", "application/json"))
    return result


def process_wazzup_payload(payload: dict) -> dict:
    if payload.get("test") is True:
        return {"status": "ok"}
    if "messages" in payload:
        converted = []
        invalid_converted = 0
        for item in payload["messages"]:
            try:
                if item.get("isEcho") or item.get("status") != "inbound" or item.get("isEdited") or item.get("isDeleted"):
                    continue
                dt = datetime.fromisoformat(item["dateTime"].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                converted.append({
                    "message_id": item["messageId"], "channel_id": item["channelId"],
                    "direction": "inbound", "timestamp": int(dt.timestamp()),
                    "text": item.get("text"),
                    "has_attachment": bool(item.get("contentUri") or item.get("type") not in (None,"text")),
                    "recipient": {"chat_id": item["chatId"], "chat_type": item["chatType"]},
                })
            except (KeyError, ValueError, TypeError, AttributeError):
                invalid_converted += 1
                continue
        payload = {"event": "message.add", "data": converted}
    elif "event" not in payload:
        return {"status": "ignored", "reason": "unsupported_event"}
    valid_data = []
    invalid_count = locals().get("invalid_converted",0)
    for raw in payload.get('data', []):
        try:
            valid_data.append(WazzupMessage.model_validate(raw))
        except (ValueError,TypeError):
            invalid_count += 1
    payload = WazzupWebhook.model_validate(dict(payload,data=valid_data))
    if payload.event != "message.add":
        return {"status": "ignored", "reason": "unsupported_event"}

    results = []
    for item in payload.data:
        if item.direction != "inbound":
            results.append({"message_id": item.message_id, "status": "ignored_outbound"})
            continue
        chat_type = (item.recipient.chat_type or "").lower()
        if chat_type not in {"vk", "max", "maxbot"}:
            results.append({"message_id": item.message_id, "status": "ignored_channel"})
            continue
        if not item.text:
            # Attachments require a human until transcription/OCR rules are approved.
            text = "Входящее сообщение содержит вложение и требует проверки администратором."
        else:
            text = item.text
        chat_id = str(item.recipient.chat_id or (item.sender.chat_id if item.sender else ""))
        sender_id = str(
            (item.sender.chat_id if item.sender else None)
            or item.recipient.phone
            or item.recipient.username
            or chat_id
        )
        message = InboundMessage(
            event_id=f"wazzup:{item.message_id}",
            channel="max" if chat_type.startswith("max") else "vk",
            chat_id=chat_id,
            sender_id=sender_id,
            branch_id=None,
            source_channel_id=item.channel_id,
            chat_type=chat_type,
            text=text,
            has_attachment=item.has_attachment or not bool(item.text),
            received_at=datetime.fromtimestamp(
                item.timestamp / 1000 if item.timestamp > 10_000_000_000 else item.timestamp,
                tz=timezone.utc,
            ),
        )
        result = inbound(message)
        if result.get("status") == "ready_to_send":
            try:
                sent = wazzup_client().send_text(
                    channel_id=item.channel_id,
                    chat_type=chat_type,
                    chat_id=chat_id,
                    text=result["answer"],
                    reply_to=item.message_id,
                    crm_message_id=str(result["inbound_id"]),
                )
                result["delivery"] = {"status": "accepted", **sent}
            except (httpx.HTTPError, WazzupError) as exc:
                result["delivery"] = {"status": "failed", "error": str(exc)}
        results.append({"message_id": item.message_id, **result})
    return {"status": "accepted", "results": results, "invalid_items": invalid_count}


@app.get("/integrations/wazzup/channels", dependencies=[Depends(require_secret)])
def wazzup_channels() -> list[dict]:
    try:
        return wazzup_client().channels()
    except (httpx.HTTPError, WazzupError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/tasks", dependencies=[Depends(require_secret)])
def tasks(status: str = "open") -> list[dict]:
    with db() as connection:
        rows = connection.execute(
            """SELECT t.*, m.channel, m.chat_id, m.sender_id, m.text
            FROM tasks t JOIN inbound_messages m ON m.id = t.inbound_id
            WHERE t.status = ? ORDER BY t.priority DESC, t.created_at ASC""",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/replies", dependencies=[Depends(require_secret)])
def replies() -> list[dict]:
    with db() as connection:
        rows = connection.execute(
            "SELECT r.*, m.text AS inbound_text, m.chat_id FROM replies r "
            "JOIN inbound_messages m ON m.id=r.inbound_id ORDER BY r.id DESC LIMIT 100"
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/tasks/{task_id}/resolve", dependencies=[Depends(require_secret)])
def resolve_task(task_id: int, payload: ResolveTask) -> dict:
    with db() as connection:
        cursor = connection.execute(
            "UPDATE tasks SET status='done', resolution=?, resolved_at=? WHERE id=? AND status='open'",
            (payload.resolution, utcnow(), task_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Open task not found")
    return {"status": "done", "task_id": task_id}


@app.post("/jobs/morning-summary", dependencies=[Depends(require_secret)])
def morning_summary() -> dict:
    open_tasks = tasks("open")
    if not open_tasks:
        return {"count": 0, "text": "Доброе утро! Открытых обращений нет."}

    lines = [f"Доброе утро! Открытых задач: {len(open_tasks)}."]
    branches: dict[str, list[dict]] = {}
    for task in open_tasks:
        branches.setdefault(str(task["branch_id"] or "не определён"), []).append(task)
    for branch, items in branches.items():
        lines.append(f"\nФилиал {branch}: {len(items)}")
        for item in items:
            lines.append(
                f"- #{item['id']} [{item['channel']}] {item['summary']}"
            )
    lines.append("\nСначала проверьте задачи без филиала и обращения с высоким приоритетом.")
    return {"count": len(open_tasks), "text": "\n".join(lines)}

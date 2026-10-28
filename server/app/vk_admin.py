"""Private VK community bot for the senior administrator, independent of Wazzup."""
from __future__ import annotations

import hashlib
import re
import json
import logging
import time

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from .main import db, init_db, utcnow
from . import report_delivery


class AdminSettings(BaseSettings):
    vk_admin_token: str = ""
    vk_admin_group_id: int = 0
    vk_admin_user_id: int = 0
    vk_api_version: str = "5.199"
    vk_admin_receive_commands: bool = False
    crm_home_url: str = "https://kodologiyapiksel.s20.online/company/1/wazzup/index"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class VKError(Exception):
    def __init__(self, code: int):
        super().__init__(f"VK API error code {code}")


REASONS={
'KNOWLEDGE_GAP':'Применимый сценарий действительно не найден',
'MISSING_CRM_FACTS':'Нужна проверка данных или действие в CRM',
'MISSING_CUSTOMER_DATA':'Нужно уточнить данные клиента',
'SCENARIO_CLARIFICATION':'Найден возможный сценарий, нужно подтвердить смысл',
'SCENARIO_READY':'Найден сценарий; черновик ожидает проверки',
'MULTI_INTENT_CLARIFICATION':'Нужно уточнить несколько намерений',
'MANDATORY_HANDOFF':'Передача по регламенту сценария',
'EXPLICIT_HUMAN_REQUEST':'Клиент явно запросил человека',
'HUMAN_ACTIVE':'Диалог остаётся под управлением человека',
'HUMAN_HANDOFF_PENDING':'Запрос человека ожидает принятия администратором',
'SAFETY_RISK':'Срочная проверка безопасности ребёнка',
'COMPLAINT':'Жалоба или спор требует человека',
'ATTACHMENT_REVIEW':'Вложение не прочитано, нужна ручная проверка',
}
def format_notification(row):
    trace=json.loads(row['trace_json']) if row['trace_json'] else {}
    reason=trace.get('reason_code','LEGACY_UNCLASSIFIED')
    label=REASONS.get(reason,'Техническая проблема знаний' if reason.startswith('KNOWLEDGE_') else 'Нужен ручной разбор')
    keys=row.keys()
    client=row['client_text'] if 'client_text' in keys else row['summary'] if 'summary' in keys else 'Текст не передан в уведомление'
    if reason=='SOURCE_DELETED':client='Сообщение удалено отправителем.'
    client=str(client or 'Сообщение без текста')
    if len(client)>1300:client=client[:1250]+'… [сообщение сокращено; полный текст в CRM]'
    answer=trace.get('draft')
    if not answer:
        answer={'KNOWLEDGE_GAP':'Готовый ответ не подобран: нужен разбор смысла обращения по книге.',
                'HUMAN_ACTIVE':'Ответ должен подготовить сотрудник, который ведёт этот диалог.',
                'HUMAN_HANDOFF_PENDING':'Клиент запросил человека. Ответ пока не подготовлен.',
                'SOURCE_DELETED':'Ответ не готовится: исходное сообщение удалено.',
                'ATTACHMENT_REVIEW':'Сначала нужно прочитать вложение; его содержимое не распознано.'}.get(reason,'Готовый ответ не подготовлен: '+label+'.')
    answer=str(answer)
    if len(answer)>1700:answer=answer[:1650]+'… [черновик сокращён]'
    text=f"Сообщение клиента:\n{client}\n\nОтвет Евы (черновик):\n{answer}"
    if trace.get('scenario'):text+=f"\n\nСценарий: {trace['scenario']}"
    if trace.get('sources'):text+='\nИсточник: '+', '.join(trace['sources'])
    if reason not in {'SCENARIO_READY','MISSING_CUSTOMER_DATA'}:text+='\nПроверка перед отправкой: '+label
    text+=f"\n\nЗадача #{row['task_id']}. Клиенту не отправлено."
    return text[:4000]


class AdminBot:
    def __init__(self, config: AdminSettings):
        self.config = config
        self.client = httpx.Client(timeout=20)

    def api(self, method: str, **params):
        response = self.client.post(
            f"https://api.vk.com/method/{method}",
            data={**params, "access_token": self.config.vk_admin_token, "v": self.config.vk_api_version},
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise VKError(result["error"].get("error_code", 0))
        return result["response"]

    def send(self, text: str, event_key: str):
        # Stable per delivery: retry after timeout must not send a duplicate.
        random_id = int.from_bytes(hashlib.sha256(event_key.encode()).digest()[:4], "big") & 0x7fffffff
        return self.api("messages.send", peer_id=self.config.vk_admin_user_id,
                        message=text[:4000], random_id=random_id or 1, dont_parse_links=1)

    def prepare(self):
        init_db()
        with db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS vk_admin_deliveries (
                    task_id INTEGER NOT NULL, recipient INTEGER NOT NULL, group_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, message_id INTEGER, last_error TEXT,
                    sent_at TEXT, PRIMARY KEY(task_id, recipient, group_id)
                );
                CREATE TABLE IF NOT EXISTS vk_admin_commands (
                    event_id TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TEXT NOT NULL,
                    sent INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS vk_admin_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    def notify(self):
        report_delivery.deliver(self)
        boundary=report_delivery.legacy_boundary()
        with db() as connection:
            connection.execute('''INSERT OR IGNORE INTO vk_admin_deliveries(task_id, recipient, group_id)
                SELECT id, ?, ? FROM tasks WHERE status='open' AND inbound_id<=? AND EXISTS(SELECT 1 FROM routing_audit a WHERE a.inbound_id=tasks.inbound_id) AND NOT EXISTS (SELECT 1 FROM vk_admin_deliveries old WHERE old.task_id=tasks.id AND old.status='sent') ''',
                (self.config.vk_admin_user_id, self.config.vk_admin_group_id, boundary))
            rows = connection.execute('''SELECT d.*, t.summary, t.category, m.channel, m.chat_id, m.text AS client_text, a.trace_json
                FROM vk_admin_deliveries d JOIN tasks t ON t.id=d.task_id
                JOIN inbound_messages m ON m.id=t.inbound_id LEFT JOIN routing_audit a ON a.inbound_id=t.inbound_id
                WHERE d.status='pending' AND d.recipient=? AND d.group_id=?
                AND t.inbound_id<=? AND d.next_attempt<=? AND t.status='open' ORDER BY t.priority DESC, t.id LIMIT 3''',
                (self.config.vk_admin_user_id, self.config.vk_admin_group_id, boundary, time.time())).fetchall()
        for row in rows:
            text = format_notification(row)

            try:
                message_id = self.send(text, f"task:{self.config.vk_admin_group_id}:{row['recipient']}:{row['task_id']}")
                with db() as connection:
                    connection.execute('''UPDATE vk_admin_deliveries SET status='sent', message_id=?, sent_at=?,
                        attempts=attempts+1, last_error=NULL WHERE task_id=? AND recipient=? AND group_id=?''',
                        (message_id, utcnow(), row['task_id'], row['recipient'], row['group_id']))
            except (httpx.HTTPError, VKError) as exc:
                # Do not log exceptions containing URLs, tokens or customer message text.
                error = str(exc) if isinstance(exc, VKError) else type(exc).__name__
                with db() as connection:
                    connection.execute('''UPDATE vk_admin_deliveries SET attempts=attempts+1, last_error=?,
                        next_attempt=? WHERE task_id=? AND recipient=? AND group_id=?''',
                        (error, time.time() + min(3600, 30 * 2 ** min(row['attempts'], 7)),
                         row['task_id'], row['recipient'], row['group_id']))
                logging.warning("Administrator notification deferred: %s", error)
            time.sleep(0.4)

    def handle(self, event: dict):
        if event.get("type") != "message_new" or event.get("group_id") != self.config.vk_admin_group_id:
            return
        message = event.get("object", {}).get("message", {})
        # Only private messages from the explicitly configured administrator.
        if message.get("from_id") != self.config.vk_admin_user_id or message.get("peer_id") != self.config.vk_admin_user_id:
            return
        event_id = f"{self.config.vk_admin_group_id}:{message['id']}"
        with db() as connection:
            previous = connection.execute("SELECT * FROM vk_admin_commands WHERE event_id=?", (event_id,)).fetchone()
            if previous:
                answer = previous['response']
                if previous['sent']:
                    return
            else:
                text = message.get('text', '').strip()
                if text.lower().startswith('/взять '):
                    number=text.split(maxsplit=1)[1].strip()
                    if not re.fullmatch(r'[0-9]{1,18}',number) or int(number)<1:
                        answer='Формат: /взять 123'
                    else:
                        row=connection.execute("SELECT m.* FROM tasks t JOIN inbound_messages m ON m.id=t.inbound_id WHERE t.id=? AND t.status='open'",(int(number),)).fetchone()
                        if row:
                            key=hashlib.sha256(json.dumps([row['channel'],row['source_channel_id'],row['chat_type'],row['chat_id'],row['branch_id']]).encode()).hexdigest()
                            connection.execute('INSERT OR REPLACE INTO conversation_control VALUES(?,?)',(key,'HUMAN_ACTIVE'))
                            answer='Диалог принят администратором. Закрытие задачи не возвращает управление боту.'
                        else:answer='Открытая задача не найдена.'
                elif text.lower() in {'/задачи', 'задачи'}:
                    rows = connection.execute("SELECT id, summary FROM tasks WHERE status='open' ORDER BY priority DESC, id LIMIT 15").fetchall()
                    answer = 'Открытые задачи:\n' + '\n'.join(f"#{r['id']}: {r['summary']}" for r in rows) if rows else 'Открытых задач нет.'
                elif text.lower().startswith('/закрыть '):
                    parts = text.split(maxsplit=2)
                    if len(parts) != 3 or not re.fullmatch(r'[0-9]{1,18}', parts[1]) or (parts[1].isascii() and parts[1].isdigit() and int(parts[1])<1) or len(parts[2]) > 2000:
                        answer = 'Формат: /закрыть 123 описание решения (до 2000 символов)'
                    else:
                        cursor = connection.execute("UPDATE tasks SET status='done', resolution=?, resolved_at=? WHERE id=? AND status='open'",
                                                    (parts[2], utcnow(), int(parts[1])))
                        answer = f"Задача #{parts[1]} закрыта." if cursor.rowcount else 'Открытая задача с таким номером не найдена.'
                else:
                    answer = ('Я Ева, помощник старшего администратора.\n/задачи — открытые обращения\n'
                              '/закрыть 123 описание решения — закрыть задачу\n'
                              'Ответы клиентам отправляйте в CRM. Сообщения из этого чата клиентам не пересылаются.')
                connection.execute("INSERT INTO vk_admin_commands(event_id,response,created_at) VALUES(?,?,?)", (event_id, answer, utcnow()))
        self.send(answer, 'command:' + event_id)
        with db() as connection:
            connection.execute("UPDATE vk_admin_commands SET sent=1 WHERE event_id=?", (event_id,))

    def run(self):
        self.prepare()
        server = None
        ts = None
        with db() as connection:
            state = connection.execute("SELECT value FROM vk_admin_state WHERE key=?", (str(self.config.vk_admin_group_id),)).fetchone()
            if state:
                ts = state['value']
        while True:
            try:
                self.notify()
                if not self.config.vk_admin_receive_commands:
                    time.sleep(10)
                    continue
                if server is None:
                    server = self.api('groups.getLongPollServer', group_id=self.config.vk_admin_group_id)
                    ts = ts or server['ts']
                    if not server['server'].startswith('https://'):
                        raise RuntimeError('VK Long Poll server must use HTTPS')
                response = self.client.get(server['server'], params={'act': 'a_check', 'key': server['key'], 'ts': ts, 'wait': 10})
                response.raise_for_status()
                events = response.json()
                if events.get('failed') == 1:
                    ts = events['ts']
                elif events.get('failed'):
                    server = None
                    if events['failed'] == 3:
                        ts = None
                    continue
                else:
                    for event in events.get('updates', []):
                        self.handle(event)
                    ts = events['ts']
                with db() as connection:
                    connection.execute('INSERT OR REPLACE INTO vk_admin_state(key,value) VALUES(?,?)',
                                       (str(self.config.vk_admin_group_id), str(ts)))
            except Exception as exc:
                logging.warning('VK worker retry: %s', str(exc) if isinstance(exc, VKError) else type(exc).__name__)
                server = None
                time.sleep(15)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    configuration = AdminSettings()
    if not configuration.vk_admin_token or configuration.vk_admin_group_id <= 0 or configuration.vk_admin_user_id <= 0:
        raise SystemExit('Configure VK_ADMIN_TOKEN, VK_ADMIN_GROUP_ID and VK_ADMIN_USER_ID before starting')
    AdminBot(configuration).run()

"""Durable, fixed-recipient staff handoff; entirely local, no CRM operations."""
import time
import re
from .main import db, utcnow

SENIOR = 446480298
OWNER = 385582430
GROUP = 168522500
ACK = 'Сейчас уточню у преподавателя и вернусь к вам с ответом.'
GENERIC_ACK = 'Сейчас уточню этот вопрос и вернусь к вам с ответом.'


class HandoffQueue:
    def prepare(self):
        with db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS private_handoffs (
                    id INTEGER PRIMARY KEY, trigger_turn INTEGER NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL, reason TEXT NOT NULL, context TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
                    notified_at TEXT, closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS private_handoff_messages (
                    turn_id INTEGER PRIMARY KEY, handoff_id INTEGER NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
                    message_id INTEGER, last_error TEXT, sent_at TEXT
                );
            ''')

    def active(self):
        with db() as c:
            return c.execute("SELECT * FROM private_handoffs WHERE owner_id=? AND status IN ('pending','notified') ORDER BY id DESC LIMIT 1", (OWNER,)).fetchone()

    def submit(self, turn_id, reason, context):
        with db() as c:
            c.execute('INSERT OR IGNORE INTO private_handoffs(trigger_turn,owner_id,reason,context,created_at) VALUES(?,?,?,?,?)',
                      (turn_id,OWNER,reason,context[:1800],utcnow()))
            ticket = c.execute('SELECT * FROM private_handoffs WHERE trigger_turn=?',(turn_id,)).fetchone()
            c.execute('INSERT OR IGNORE INTO private_handoff_messages(turn_id,handoff_id,kind) VALUES(?,?,?)',
                      (turn_id,ticket['id'],'trigger'))
            # Incoming events can arrive as a batch before generation starts.
            c.execute("INSERT OR IGNORE INTO private_handoff_messages(turn_id,handoff_id,kind) SELECT id,?,'followup' FROM private_turns WHERE id>? AND sent=0",(ticket['id'],turn_id))

    def attach(self, turn_id, ticket_id):
        with db() as c:
            row = c.execute('SELECT text FROM private_turns WHERE id=?',(turn_id,)).fetchone()
            if self.ack_only(row['text']):
                c.execute("UPDATE private_turns SET sent=1,answer='' WHERE id=?",(turn_id,))
                return
            c.execute('INSERT OR IGNORE INTO private_handoff_messages(turn_id,handoff_id,kind) VALUES(?,?,?)',
                      (turn_id,ticket_id,'followup'))

    @staticmethod
    def ack_only(text):
        value = re.sub(r'[^\w+\s]','',text.lower()).strip()
        return value in {'спасибо','спасибо большое','большое спасибо','спасибо жду','ок','okay','ok','хорошо','+','да','понятно','ладно','жду','жду ответа'}

    def cancel_for_reset(self):
        with db() as c:
            c.execute("UPDATE private_handoffs SET status='cancelled',closed_at=? WHERE owner_id=? AND status IN ('pending','notified')",(utcnow(),OWNER))
            c.execute("UPDATE private_handoff_messages SET status='cancelled' WHERE status='pending' AND handoff_id IN (SELECT id FROM private_handoffs WHERE status='cancelled')")
            c.execute("UPDATE private_turns SET sent=1,answer=coalesce(answer,'') WHERE sent=0 AND id IN (SELECT turn_id FROM private_handoff_messages WHERE status='cancelled')")

    def close(self, ticket_id):
        with db() as c:
            changed = c.execute("UPDATE private_handoffs SET status='closed',closed_at=? WHERE id=? AND owner_id=? AND status='notified'", (utcnow(),ticket_id,OWNER)).rowcount
        return bool(changed)

    def notify(self, sender):
        with db() as c:
            rows = c.execute('''SELECT m.*, h.owner_id,h.status AS ticket_status,h.context,t.text
                FROM private_handoff_messages m JOIN private_handoffs h ON h.id=m.handoff_id
                JOIN private_turns t ON t.id=m.turn_id
                WHERE m.status='pending' AND h.status IN ('pending','notified','closed')
                AND m.next_attempt<=? ORDER BY m.turn_id LIMIT 3''',(time.time(),)).fetchall()
        for row in rows:
            if row['owner_id'] != OWNER:
                raise RuntimeError('Handoff owner blocked')
            if row['kind']=='followup' and self.ack_only(row['text']):
                with db() as c:
                    c.execute("UPDATE private_handoff_messages SET status='ignored' WHERE turn_id=?",(row['turn_id'],))
                    c.execute("UPDATE private_turns SET sent=1,answer='' WHERE id=?",(row['turn_id'],))
                continue
            heading = 'Нужен ответ клиенту' if row['kind']=='trigger' else 'Дополнение от клиента'
            text = (f"Ева: {heading}\nОбращение #{row['handoff_id']}\n"
                    f"Клиент: https://vk.ru/id{OWNER}\n"
                    f"Диалог сообщества: https://vk.ru/gim{GROUP}?sel={OWNER}\n\n"
                    f"Вопрос клиента:\n{row['text'][:1000]}\n\n")
            if row['kind']=='trigger':
                text += f"Контекст беседы:\n{row['context']}\n\n"
            text += ("Ответьте клиенту самостоятельно от имени сообщества. "
                     "Автоматические ответы Евы в этом диалоге приостановлены.\n"
                     f"После ответа напишите сюда: /готово {row['handoff_id']}\n"
                     "Это личный тест интеграции; остальные клиентские чаты не подключены.")
            try:
                message_id = sender(text, f"handoff:{row['handoff_id']}:{row['turn_id']}", row['handoff_id'])
            except Exception as exc:
                # Type only: never log token URLs, message text or model payload.
                error = type(exc).__name__
                with db() as c:
                    c.execute('UPDATE private_handoff_messages SET attempts=attempts+1,last_error=?,next_attempt=? WHERE turn_id=?',
                              (error,time.time()+min(300,5*2**min(row['attempts'],6)),row['turn_id']))
                continue
            with db() as c:
                c.execute("UPDATE private_handoff_messages SET status='sent',message_id=?,sent_at=?,last_error=NULL WHERE turn_id=?",(message_id,utcnow(),row['turn_id']))
                if row['kind']=='trigger':
                    c.execute("UPDATE private_handoffs SET status='notified',notified_at=? WHERE id=? AND status='pending'",(utcnow(),row['handoff_id']))
                else:
                    # Forwarded to the human; no automated customer reply.
                    c.execute("UPDATE private_turns SET sent=1,answer='',sent_at=? WHERE id=?",(utcnow(),row['turn_id']))

    def delivery(self, turn_id):
        with db() as c:
            return c.execute('SELECT * FROM private_handoff_messages WHERE turn_id=?',(turn_id,)).fetchone()

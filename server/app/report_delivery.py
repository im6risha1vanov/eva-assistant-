"""Authorized two-recipient reports; called by the existing VK sender only."""
import json,sqlite3,time,hashlib,logging
from pathlib import Path
CONFIG=Path('/etc/eva-admin-reports.json')
DB=Path('/var/lib/eva/admin_reports/reports.db')
def config():
    if not CONFIG.exists():return None
    d=json.loads(CONFIG.read_text())
    if not d.get('enabled'):return None
    if set(d.get('recipients',[]))!={463369175,385582430}:raise RuntimeError('RECIPIENT_ALLOWLIST_MISMATCH')
    return d
def legacy_boundary():
    d=config();return d['baseline_inbound_id'] if d else 9223372036854775807
def random_id(group,event,recipient,part):
    return (int.from_bytes(hashlib.sha256(f"semantic-report:{group}:{event}:{recipient}:{part}".encode()).digest()[:4],'big')&0x7fffffff) or 1
def deliver(bot):
    d=config()
    if not d or not DB.exists():return
    c=sqlite3.connect(DB,timeout=10);c.row_factory=sqlite3.Row
    try:
        rows=c.execute("SELECT * FROM deliveries WHERE status='pending' AND next_attempt<=? ORDER BY event_key,recipient,part LIMIT 6",(time.time(),)).fetchall()
        for row in rows:
            if row['recipient'] not in d['recipients']:raise RuntimeError('DELIVERY_RECIPIENT_FORBIDDEN')
            try:
                mid=bot.api('messages.send',peer_id=row['recipient'],message=row['body'],random_id=random_id(bot.config.vk_admin_group_id,row['event_key'],row['recipient'],row['part']),dont_parse_links=1)
                with c:c.execute("UPDATE deliveries SET status='sent',message_id=?,attempts=attempts+1,error=NULL,sent_at=? WHERE event_key=? AND recipient=? AND part=?",(mid,time.time(),row['event_key'],row['recipient'],row['part']))
            except Exception as e:
                with c:c.execute("UPDATE deliveries SET attempts=attempts+1,error=?,next_attempt=? WHERE event_key=? AND recipient=? AND part=?",(type(e).__name__,time.time()+min(3600,30*2**min(row['attempts'],7)),row['event_key'],row['recipient'],row['part']))
                logging.warning('Private report delivery deferred: %s',type(e).__name__)
            time.sleep(0.4)
    finally:c.close()

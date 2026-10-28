"""Read-only incoming observer and draft report builder. No CRM/customer sender."""
import os,sys,json,time,sqlite3,hashlib,uuid,urllib.parse,logging
from pathlib import Path
from datetime import datetime,timezone
import semantic_core as core
core.COMMON.update("Онлайн Офлайн Очно Заочно Сочувствую Если Напишите Уточните Подскажите История Физика Химия Алгебра Геометрия Биология География Литература Договор Оплата Занятия Занятие Выздоравливайте Рада Желаем Давайте Сможете Вижу Извините Чтобы Отлично Подойдёт Подтвердите Расскажите Принято Жаль Сожалею Платёж Пробное Можете Оплату Обращайтесь Обычно После Свяжитесь Квитанция Ссылка Клиент Клиентка Ученик Ученица Родитель Просит Попросил Попросила Сообщает Согласен Согласна Хочет Запросил Запрашивает Подтверждает Отказывается Интересуется Благодарит Сообщение Вопрос Ответ".split())
CONFIG=Path('/etc/eva-admin-reports.json')
DB=Path('/var/lib/eva/admin_reports/reports.db')
PRIVATE=Path('/var/lib/eva-admin-reports')
SCHEMA="""
CREATE TABLE IF NOT EXISTS reports(event_key TEXT PRIMARY KEY,source_id INTEGER,source_kind TEXT,status TEXT,input_json TEXT,summary TEXT,draft TEXT,error TEXT,created REAL,finished REAL);
CREATE TABLE IF NOT EXISTS deliveries(event_key TEXT,recipient INTEGER,part INTEGER,body TEXT,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,message_id INTEGER,error TEXT,sent_at REAL,PRIMARY KEY(event_key,recipient,part));
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
"""
def connect(path=DB,ro=False):
    c=sqlite3.connect('file:'+str(path)+'?mode=ro' if ro else str(path),uri=ro,timeout=15);c.row_factory=sqlite3.Row;return c
def now():return datetime.now(timezone.utc).isoformat()
def message_id(value):
    value=str(value)
    return value[7:] if value.startswith('wazzup:') else value
def identity(channel,kind,chat,message):return core.digest([str(channel or ''),str(kind or '').lower(),str(chat or ''),message_id(message)])
def privacy(text):
    import re
    text=str(text or '')
    text=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----','[закрытый ключ скрыт]',text,flags=re.S)
    return re.sub(r'(?i)(?:sk-[\w-]{16,}|Bearer\s+[\w.-]{16,}|(?:token|api_key|secret)\s*[:=]\s*[\w.-]{12,})','[секрет скрыт]',text)
def split_report(client,summary,draft,ref,limit=3500):
    text=f"Как написал клиент:\n{privacy(client)}\n\nКак я это понял:\n{privacy(summary)}\n\nЧто бы я ответил (черновик):\n{privacy(draft)}\n\n{ref}. Клиенту не отправлено."
    chunks=[text[i:i+limit] for i in range(0,len(text),limit)]
    return [((f"Часть {i+1}/{len(chunks)}\n" if len(chunks)>1 else '')+x) for i,x in enumerate(chunks)]
class PerEventUsage(core.Usage):
    """One reserved call per durable source job; no unrequested historical sweep."""
    def reserve(self,purpose,model):
        ident=uuid.uuid4().hex
        with self.db() as c:c.execute('INSERT INTO calls(id,purpose,created,status,model) VALUES(?,?,?,?,?)',(ident,purpose,time.time(),'reserved',model))
        return ident
    def finish(self,ident,status,usage=None,latency=0,error=None):
        usage=usage or {}
        with self.db() as c:c.execute('UPDATE calls SET status=?,input_tokens=COALESCE(?,input_tokens),output_tokens=COALESCE(?,output_tokens),latency=?,provider_cost=COALESCE(?,provider_cost),error=? WHERE id=?',(status,usage.get('prompt_tokens'),usage.get('completion_tokens'),latency,usage.get('cost'),error,ident))
def context(source,cap,job):
    data=json.loads(job['input_json']);stamp=data['timestamp'];channel=data['channel'];kind=data['chat_type'];chat=data['chat_id'];branch=data.get('branch_id')
    history=[]
    if data.get('source_id'):
        rows=source.execute("""SELECT id,event_id,text,received_at FROM inbound_messages WHERE source_channel_id IS ? AND chat_type IS ? AND chat_id=? AND branch_id IS ? AND channel=?
            AND (julianday(received_at)<julianday(?) OR (julianday(received_at)=julianday(?) AND id<?)) ORDER BY julianday(received_at) DESC,id DESC LIMIT 19""",(channel,kind,chat,branch,data['app_channel'],stamp,stamp,data['source_id'])).fetchall()
        for r in rows:history.append({'ref':core.digest(['app',r['id']]),'role':'client_reported','text':r['text'],'time':r['received_at']})
    if cap:
        rows=cap.execute("""SELECT * FROM events WHERE channel_id IS ? AND chat_type IS ? AND chat_id=?
             AND julianday(timestamp)<=julianday(?) ORDER BY julianday(received_at) DESC LIMIT 400""",(channel,kind,chat,stamp)).fetchall()
        latest={}
        for r in rows:latest.setdefault(str(r['message_id']),r)
        recent=sorted(latest.values(),key=lambda r:r['timestamp'],reverse=True)
        counts={'inbound':0,'outbound':0}
        for r in recent:
            direction=r['direction']
            if r['deleted'] or str(r['message_id'])==str(data['message_id']) or direction not in counts:continue
            if counts[direction]>=(0 if data.get('source_id') else 19) and direction=='inbound':continue
            if direction=='outbound' and counts[direction]>=10:continue
            counts[direction]+=1
            history.append({'ref':core.digest(['captured',r['event_key']]),'role':'client_reported' if direction=='inbound' else 'outbound_author_unverified','text':r['text'] or '[вложение не распознано]','time':r['timestamp'],'attachment_unknown':bool(r['content_uri'])})
        # A deletion in capture suppresses the same source from local history.
        deleted={str(r['message_id']) for r in latest.values() if r['deleted']}
        if deleted and data.get('source_id'):
            bad={core.digest(['app',r['id']]) for r in source.execute('SELECT id,event_id FROM inbound_messages WHERE source_channel_id IS ? AND chat_id=? AND chat_type IS ?',(channel,chat,kind)) if message_id(r['event_id']) in deleted}
            history=[h for h in history if h['ref'] not in bad]
        current_version=latest.get(str(data['message_id']))
        if current_version:
            if current_version['deleted']:raise core.AgentError('SOURCE_DELETED')
            if current_version['edited']:data['text']=current_version['text'] or ''
            data['attachment_unknown']=bool(current_version['content_uri'])
    def timestamp(v):
        try:return datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
        except Exception:return 0
    history.sort(key=lambda h:(timestamp(h['time']),h['ref']))
    current={'ref':job['event_key'],'role':'client_reported','text':data['text'],'attachment_unknown':bool(data.get('attachment_unknown'))}
    human=False
    if data.get('source_id'):
        key=hashlib.sha256(json.dumps([data['app_channel'],channel,kind,chat,branch],ensure_ascii=False).encode()).hexdigest()
        row=source.execute('SELECT state FROM conversation_control WHERE conversation_key=?',(key,)).fetchone()
        human=bool(row and row['state'] in ['HUMAN_ACTIVE','HUMAN_REQUESTED'])
    return data,current,history,human
def discover(c,cfg):
    src=connect('/var/lib/eva/bot.db',True)
    try:
        for r in src.execute('SELECT * FROM inbound_messages WHERE id>? ORDER BY id',(cfg['baseline_inbound_id'],)):
            d={'source_id':r['id'],'app_channel':r['channel'],'channel':r['source_channel_id'],'chat_type':r['chat_type'],'chat_id':r['chat_id'],'branch_id':r['branch_id'],'message_id':message_id(r['event_id']),'timestamp':r['received_at'],'text':r['text']}
            key=identity(d['channel'],d['chat_type'],d['chat_id'],d['message_id'])
            c.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?, ?,?,NULL,NULL,NULL,?,NULL)',(key,r['id'],'app','pending',core.canonical(d),time.time()))
    finally:src.close()
    capture=Path('/var/lib/eva-salesbook-monitor/conversation_events.db')
    if capture.exists():
        cap=connect(capture,True)
        try:
            for r in cap.execute("""SELECT * FROM events WHERE direction='inbound' AND julianday(received_at)>=julianday(?) AND julianday(received_at)<julianday(?)
                    ORDER BY julianday(received_at)""",(cfg['start_at'],datetime.fromtimestamp(time.time()-60,timezone.utc).isoformat())):
                if r['deleted'] or (r['edited'] and r['timestamp']<cfg['start_at']):continue
                d={'source_id':None,'channel':r['channel_id'],'chat_type':r['chat_type'],'chat_id':r['chat_id'],'message_id':r['message_id'],'timestamp':r['timestamp'],'text':r['text'] or '[вложение не распознано]','attachment_unknown':bool(r['content_uri'])}
                c.execute('INSERT OR IGNORE INTO reports VALUES(?,NULL,?,?,?,NULL,NULL,NULL,?,NULL)',(identity(d['channel'],d['chat_type'],d['chat_id'],d['message_id']),'capture','pending',core.canonical(d),time.time()))
        finally:cap.close()
    c.commit()
def publish(c,job,data,summary,draft,error,cfg):
    ref='Сообщение #'+str(job['source_id']) if job['source_id'] else 'Входящее '+job['event_key'][:10]
    chunks=split_report(data.get('text','Сообщение недоступно'),summary,draft,ref)
    with c:
        c.execute('UPDATE reports SET status=?,summary=?,draft=?,error=?,finished=? WHERE event_key=?',('failed' if error else 'ready',summary,draft,error,time.time(),job['event_key']))
        for recipient in cfg['recipients']:
            for part,body in enumerate(chunks):c.execute('INSERT OR IGNORE INTO deliveries(event_key,recipient,part,body) VALUES(?,?,?,?)',(job['event_key'],recipient,part,body))
def refresh_regulation():
    # Only GET; sheet writer and existing monitor's run() are never called.
    sys.path.insert(0,'/opt/eva-salesbook-monitor')
    import server_monitor
    metadata=server_monitor.sheet('GET','?fields=sheets.properties.title')
    titles=[x['properties']['title'] for x in metadata['sheets']]
    suffix='/values:batchGet?'+urllib.parse.urlencode([('ranges',"'"+t.replace("'","''")+"'") for t in titles]+[('valueRenderOption','FORMATTED_VALUE')])
    values=server_monitor.sheet('GET',suffix)
    if len(values.get('valueRanges',[]))!=len(titles):raise core.AgentError('BOOK_PARTIAL_READ')
    reg=core.compile_regulation({t:v.get('values',[]) for t,v in zip(titles,values['valueRanges'])})
    core.atomic(PRIVATE/'regulation.json',reg);return reg
def analyse(c,job,cfg,provider):
    src=connect('/var/lib/eva/bot.db',True);cap=None;data=json.loads(job['input_json'])
    try:
        cp=Path('/var/lib/eva-salesbook-monitor/conversation_events.db')
        if cp.exists():cap=connect(cp,True)
        data,current,history,human=context(src,cap,job)
        reg=core.read_regulation(PRIVATE/'regulation.json');engine=core.Engine(reg,provider)
        payload=engine.payload(current,history,human)
        if len(core.canonical(payload))>180000:raise core.AgentError('CONTEXT_TOO_LARGE')
        with c:c.execute("UPDATE reports SET status='model_started' WHERE event_key=?",(job['event_key'],))
        messages=[{'role':'system','content':core.SYSTEM},{'role':'user','content':core.canonical(payload)}]
        # Retry only when the gateway refused or was unreachable, so no answer was produced; timeouts stay single-shot.
        for attempt in range(3):
            try:result,call=provider.request(messages,purpose='live_report',max_tokens=2500);break
            except core.AgentError as e:
                if str(e) not in core.RETRYABLE or attempt==2:raise
                time.sleep(20*(attempt+1))
        core.atomic(PRIVATE/'results'/str(job['event_key']+'.json'),{'result':result,'call_id':call,'history_count':len(history),'policy_version':reg['version']})
        refs={x['ref'] for x in payload['conversation']}
        result,notes=core.repair(result,reg,refs)
        try:checked=core.validate(result,reg,refs,human)
        except core.AgentError as e:
            # A missing scenario is reported to the administrator instead of discarding the draft.
            if str(e)!='MODEL_SCENARIO_REQUIRED':raise
            temp=dict(result,decision='knowledge_gap');checked=core.validate(temp,reg,refs,human);checked['decision']=result['decision']
        summary=checked['summary']
        if notes:summary+='\nПроверка: '+'; '.join(notes)+'.'
        if human:summary+='\nДиалог передан человеку; управление остаётся у сотрудника.'
        if not history:summary+='\nПредыдущая история в доступном источнике отсутствует.'
        if current.get('attachment_unknown'):summary+='\nСодержимое вложения не распознано.'
        publish(c,job,data,summary,checked['draft'],None,cfg)
    except Exception as e:
        code=str(e) if isinstance(e,core.AgentError) else type(e).__name__
        if code=='SOURCE_DELETED':
            data['text']='Сообщение удалено отправителем.'
            summary='Исходное сообщение удалено. Его текст не использован.'
            draft='Ответ не составляю: источник удалён.'
        else:
            summary='Автоматический разбор не завершён: '+code+'. Нельзя утверждать, что смысл сообщения определён.'
            draft='Черновик не готов. Нужен ручной разбор сотрудником; клиенту ничего не отправлено.'
        publish(c,job,data,summary,draft,code,cfg)
    finally:
        src.close()
        if cap:cap.close()
def status(c):
    return {'reports':[dict(r) for r in c.execute('SELECT status,count(*) count FROM reports GROUP BY status')],'deliveries':[dict(r) for r in c.execute('SELECT status,count(*) count FROM deliveries GROUP BY status')]}
def recover(c,cfg):
    for job in c.execute("SELECT * FROM reports WHERE status='model_started'").fetchall():
        publish(c,job,json.loads(job['input_json']),'Разбор прерван перезапуском; результат и списание провайдера неизвестны.','Черновик не готов: требуется ручная проверка.','INTERRUPTED_PROVIDER_RESULT_UNKNOWN',cfg)
def main():
    os.umask(0o007);PRIVATE.mkdir(parents=True,exist_ok=True);os.chmod(PRIVATE,0o700)
    cfg=json.loads(CONFIG.read_text())
    if not cfg.get('enabled'):raise SystemExit('DISABLED')
    if set(cfg['recipients'])!={100000001,100000002}:raise SystemExit('RECIPIENT_ALLOWLIST_MISMATCH')
    c=connect();c.executescript(SCHEMA);os.chmod(DB,0o660)
    provider=core.Provider(PerEventUsage(PRIVATE/'usage.db'))
    if len(sys.argv)>1 and sys.argv[1]=='status':print(json.dumps(status(c)));return
    # Ambiguous crash after a paid call must not silently issue a second paid call.
    recover(c,cfg)
    next_refresh=0
    while True:
        try:
            if time.time()>next_refresh:
                try:refresh_regulation();next_refresh=time.time()+12*3600
                except Exception:next_refresh=time.time()+3600;logging.warning('Rule refresh unavailable; existing cache retained')
            discover(c,cfg)
            job=c.execute("SELECT * FROM reports WHERE status='pending' ORDER BY created,event_key LIMIT 1").fetchone()
            if job:analyse(c,job,cfg,provider)
            else:time.sleep(5)
        except Exception as e:logging.warning('Report worker deferred: %s',type(e).__name__);time.sleep(10)
if __name__=='__main__':main()

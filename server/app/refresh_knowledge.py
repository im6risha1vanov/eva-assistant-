"""Manual refresh command; atomic data cache, no app restart or approvals."""
import json,os,sys,hashlib,fcntl
from pathlib import Path
from datetime import datetime,timezone
from urllib.error import HTTPError,URLError
from . import routing

def compile_book(book):
    try:rows=book['Сценарии']
    except KeyError:raise routing.KnowledgeError('KNOWLEDGE_SHEET_MISSING')
    expected=['ID','Сценарий','Запрос клиента','Необходимые данные','Где проверять','Проверка и действия Евы','Пример ответа']
    if not rows or rows[0][:7]!=expected:raise routing.KnowledgeError('KNOWLEDGE_HEADERS_CHANGED')
    entries=[];warnings=[]
    for i,row in enumerate(rows[1:],2):
        if not row or not row[0]:continue
        if len(row)<12 or not all(isinstance(row[n],str) and row[n].strip() for n in [0,1,3,4,5,6,9]):
            warnings.append({'row':i,'id':row[0],'reason':'CRITICAL_ROW_INVALID'});continue
        entries.append(dict(id=row[0],intent=row[1],examples=[row[2]],required_data=row[3],dependencies=row[4],next_step=row[5],answer=row[6],handoff=row[7],completion=row[8],source=f'Сценарии!A{i}:L{i}',approved=False,draft_review=True,branch_id=None))
    if not entries:raise routing.KnowledgeError('KNOWLEDGE_EMPTY')
    return {'schema':1,'version':routing.VERSION,'observed_at':datetime.now(timezone.utc).isoformat(),'book_id':'1tDWI0FZanmlgmEVAWtUiOkIo7ZREiNY473HdMqnhD8w','production_enabled':False,'entries':entries,'row_warnings':warnings,'blocked_ids':[x['id'] for x in warnings],'rules':book.get('Условия и источники',[]),'book_hash':hashlib.sha256(json.dumps(book,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}

def _refresh_unlocked(fetch,path):
    path=Path(path)
    try:release=compile_book(fetch())
    except HTTPError as e:raise routing.KnowledgeError('KNOWLEDGE_HTTP_'+str(e.code)) from e
    except (TimeoutError,URLError):raise routing.KnowledgeError('KNOWLEDGE_NETWORK_UNAVAILABLE')
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(release,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        routing.load(tmp)
        tmp.replace(path)
    finally:
        if tmp.exists():tmp.unlink()
    return {'version':release['version'],'entries':len(release['entries']),'warnings':release['row_warnings']}


def refresh(fetch,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _refresh_unlocked(fetch,path)

if __name__=='__main__':
    # Execute as root with existing service account; app worker needs no Google credential.
    sys.path.insert(0,'/opt/eva-salesbook-monitor')
    import server_monitor as m
    import urllib.parse
    def fetch():
        result={}
        for title in ['Сценарии','Условия и источники']:
            target=urllib.parse.quote("'"+title+"'",safe='')
            result[title]=m.sheet('GET','/values/'+target+'?valueRenderOption=FORMATTED_VALUE').get('values',[])
        return result
    try:print(json.dumps(refresh(fetch,sys.argv[1]),ensure_ascii=False))
    except routing.KnowledgeError as e:print(str(e));sys.exit(1)

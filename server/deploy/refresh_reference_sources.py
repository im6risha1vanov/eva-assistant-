"""Read-only Google Sheets snapshot: readonly OAuth, GET-only API, local atomic output."""
import base64, json, os, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/opt/eva')
from app.reference_sources import INDEX_ID,PRICE_ID,SCHEDULE_ID,sanitize
ROOT=Path('/var/lib/eva/reference-sources')
KEY=Path('/etc/eva-salesbook-monitor/google-service-account.json')

def token():
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    k=json.loads(KEY.read_text())
    def enc(x): return base64.urlsafe_b64encode(json.dumps(x,separators=(',',':')).encode()).rstrip(b'=')
    now=int(time.time())
    data=enc({'alg':'RS256','typ':'JWT'})+b'.'+enc({'iss':k['client_email'],'scope':'https://www.googleapis.com/auth/spreadsheets.readonly','aud':'https://oauth2.googleapis.com/token','iat':now,'exp':now+3600})
    private=serialization.load_pem_private_key(k['private_key'].encode(),password=None)
    assertion=(data+b'.'+base64.urlsafe_b64encode(private.sign(data,padding.PKCS1v15(),hashes.SHA256())).rstrip(b'=')).decode()
    body=urllib.parse.urlencode({'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer','assertion':assertion}).encode()
    with urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token',data=body),timeout=20) as r: return json.load(r)['access_token']

def get(book,suffix,access):
    if book not in {INDEX_ID,PRICE_ID,SCHEDULE_ID}: raise ValueError('Book not allowed')
    request=urllib.request.Request('https://sheets.googleapis.com/v4/spreadsheets/'+book+suffix,
        method='GET',headers={'Authorization':'Bearer '+access})
    with urllib.request.urlopen(request,timeout=25) as r: return json.load(r)

def values(book,ranges,access):
    query=urllib.parse.urlencode([('ranges',r) for r in ranges]+[('valueRenderOption','FORMATTED_VALUE')])
    data=get(book,'/values:batchGet?'+query,access)
    if len(data.get('valueRanges',[]))!=len(ranges): raise ValueError('Incomplete ranges')
    return [x.get('values',[]) for x in data['valueRanges']]

def main():
    ROOT.mkdir(mode=0o750,parents=True,exist_ok=True)
    import grp
    os.chown(ROOT,0,grp.getgrnam('eva').gr_gid)
    os.chmod(ROOT,0o750)
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'sources':{}}
    registry={
        'prices':(PRICE_ID,["'Прайс-лист 26-27'!A1:U120","'Программа лояльности'!A1:F50"]),
        'teachers':(SCHEDULE_ID,["'Педсостав 2.0'!A1:K100","'Педсостав 2.0'!P1:P100"]),
        'groups':(SCHEDULE_ID,["'Предметы'!A1:I65","'Подготовка к поступлению'!A1:B7"]),
        'grid':(SCHEDULE_ID,["'Интер'!A1:BC35","'Орбита '!A1:O35"]),
    }
    try: access=token()
    except Exception as exc:
        access=None; token_error=type(exc).__name__
    for name,(book,ranges) in registry.items():
        try:
            if access is None: raise RuntimeError(token_error)
            data=values(book,ranges,access)
            result['sources'][name]={'status':'ok','fetched_epoch':time.time(),
                'tab_names':[r.split('!')[0].strip("'") for r in ranges],'data':sanitize(name,data)}
        except Exception as exc:
            # No raw response URLs, credential values or source content in logs.
            error='HTTP_'+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__
            result['sources'][name]={'status':'error','error':error}
    output=ROOT/'current.json';tmp=ROOT/'current.json.new'
    tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    os.chmod(tmp,0o640)
    os.chown(tmp,0,grp.getgrnam('eva').gr_gid)
    tmp.replace(output)
    print(json.dumps({k:{'status':v['status'],'error':v.get('error')} for k,v in result['sources'].items()}))
    if any(source['status']!='ok' for source in result['sources'].values()):
        raise SystemExit(1)

if __name__=='__main__': main()

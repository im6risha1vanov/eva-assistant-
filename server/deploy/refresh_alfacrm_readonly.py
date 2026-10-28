"""Strictly read CRM, count locally, export no pupil identities or contact data."""
import json,os,sys,time,grp,fcntl
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,'/opt/eva')
from app.alfacrm_readonly import ReadOnlyCRM,config_from_file
from app.crm_context import summarize_group,parse_date,MOSCOW
ROOT=Path('/var/lib/eva/crm-readonly')

def main():
    ROOT.mkdir(mode=0o750,parents=True,exist_ok=True);gid=grp.getgrnam('eva').gr_gid
    os.chown(ROOT,0,gid);ROOT.chmod(0o750)
    with (ROOT/'refresh.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        now=datetime.now(MOSCOW);started=time.time();end=(now+timedelta(days=14)).date()
        crm=ReadOnlyCRM(config_from_file('/etc/eva/alfacrm.env'))
        result={'status':'ok','fetched_epoch':started,'checked_at':now.isoformat(),'window_end':end.isoformat(),'branches':[]}
        try:
            branches=crm.all('branch',filters={'is_active':1})
            for branch in branches:
                bid=branch['id']
                groups=crm.all('group',bid,{'removed':0})
                regular=crm.all('regular-lesson',bid)
                subjects={r['id']:r['name'] for r in crm.all('subject',bid)}
                teachers={r['id']:r['name'] for r in crm.all('teacher',bid)}
                rooms={r['id']:r['name'] for r in crm.all('room',bid)}
                lessons=crm.all('lesson',bid,{'status':1,'date_from':now.date().isoformat(),'date_to':end.isoformat()})
                export={'branch_id':bid,'branch':branch.get('name'),'groups':[]}
                for group in groups:
                    start=parse_date(group.get('b_date'));finish=parse_date(group.get('e_date'))
                    if finish and finish<now.date() or start and start>end: continue
                    group_regular=[r for r in regular if r.get('related_class')=='Group' and r.get('related_id')==group['id']]
                    if not group_regular: continue
                    members=crm.all('cgi',bid,group_id=group['id'])
                    export['groups'].append(summarize_group(group,members,lessons,group_regular,subjects,teachers,rooms,now))
                result['branches'].append(export)
            result['request_paths']=sorted(set(crm.requests));result['request_count']=len(crm.requests)
            result['duration_seconds']=round(time.time()-started,1)
        except Exception as exc:
            # Fail closed: old counts are never marked current; no exception text containing personal values.
            result={'status':'error','fetched_epoch':started,'checked_at':now.isoformat(),'error':type(exc).__name__,'branches':[],
                    'request_paths':sorted(set(crm.requests))}
            from app.alfacrm_readonly import CRMError
            if isinstance(exc,CRMError): result['error']=str(exc)
        tmp=ROOT/'current.json.new';tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        tmp.chmod(0o640);os.chown(tmp,0,gid);tmp.replace(ROOT/'current.json')
        print(json.dumps({'status':result['status'],'error':result.get('error'),'branches':[{ 'id':b['branch_id'],'groups':len(b['groups']),
             'known_availability':sum(g['availability_status']=='known' for g in b['groups'])} for b in result['branches']],
             'read_requests':result.get('request_count'),'duration_seconds':result.get('duration_seconds')},ensure_ascii=False),flush=True)
        if result['status']!='ok': raise SystemExit(1)

if __name__=='__main__': main()

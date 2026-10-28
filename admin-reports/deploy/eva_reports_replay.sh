#!/bin/bash
# Ева: прогон новой проверки на сохранённых ответах модели по упавшим отчётам. Только чтение, без текстов.
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import sys,json,sqlite3,collections as C
from pathlib import Path
sys.path.insert(0,'/opt/eva-admin-reports');import semantic_core as core
RETRYABLE={'LLM_HTTP_429','LLM_HTTP_500','LLM_HTTP_502','LLM_HTTP_503','LLM_HTTP_504','LLM_URLError'}
def repair(result,regulation,evidence_refs):
    """Drop bookkeeping the model got wrong; safety checks in validate() stay strict."""
    if not isinstance(result,dict) or set(result)!=core.FIELDS:return result,[]
    notes=[];result=dict(result);rules={r['rule_id']:r for r in regulation['rules']}
    result['policy_version']=regulation['version']
    rule_ids=[i for i in result['rule_ids'] if isinstance(i,str) and i in rules] if isinstance(result['rule_ids'],list) else []
    if isinstance(result['rule_ids'],list) and len(rule_ids)<len(result['rule_ids']):notes.append('ссылки на несуществующие правила убраны')
    result['rule_ids']=rule_ids;sources={rules[r]['source_id'] for r in rule_ids};result['source_ids']=sorted(sources)
    if isinstance(result['entities'],list):
        result['entities']=[e for e in result['entities'] if isinstance(e,dict) and set(e)=={'name','value','origin','evidence_ref'} and e['origin']=='client_reported' and e['evidence_ref'] in evidence_refs]
    if isinstance(result['required_actions'],list):result['required_actions']=[a for a in result['required_actions'] if a in core.ACTIONS]
    if isinstance(result['claims'],list):
        claims=[]
        for claim in result['claims']:
            if isinstance(claim,dict) and set(claim)=={'text','kind','refs'} and claim['kind'] in {'rule','client_reported'} and isinstance(claim['refs'],list):
                allowed=sources if claim['kind']=='rule' else evidence_refs
                claim=dict(claim,refs=[r for r in claim['refs'] if r in allowed])
                if not claim['refs']:notes.append('утверждения без подтверждённого источника убраны');continue
            claims.append(claim)
        result['claims']=claims
    if result['decision'] not in {'technical_incident','knowledge_gap'} and not any(i.startswith('scenario.') for i in rule_ids):notes.append('подходящий сценарий в книге продаж не найден, проверьте черновик внимательнее')
    return result,sorted(set(notes))
reg=json.loads(Path('/var/lib/eva-admin-reports/regulation.json').read_text())
c=sqlite3.connect('file:/var/lib/eva/admin_reports/reports.db?mode=ro',uri=True)
out=C.Counter();notes=C.Counter()
for key,err in c.execute("select event_key,error from reports where status='failed'"):
    f=Path('/var/lib/eva-admin-reports/results')/(key+'.json')
    if not f.exists():out[(err,'нет сохранённого ответа')]+=1;continue
    r=json.loads(f.read_text())['result']
    refs={e.get('evidence_ref') for e in r.get('entities',[]) if isinstance(e,dict)}|{x for cl in r.get('claims',[]) if isinstance(cl,dict) and cl.get('kind')=='client_reported' for x in (cl.get('refs') or [])}
    fixed,n=repair(r,reg,refs)
    try:core.validate(fixed,reg,refs);res='прошёл'
    except core.AgentError as e:
        res=str(e)
        if res=='MODEL_SCENARIO_REQUIRED':
            try:core.validate(dict(fixed,decision='knowledge_gap'),reg,refs);res='прошёл'
            except core.AgentError as e2:res=str(e2)
    out[(err,res)]+=1
    for x in n:notes[x]+=1
print('== было -> стало')
for k,v in out.most_common():print('  %4d  %s -> %s'%(v,*k))
print('== пометки администратору')
for k,v in notes.most_common():print('  %4d  %s'%(v,k))
PY

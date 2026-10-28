"""Deterministic draft routing; no client sends or external mutations."""
import json,re,hashlib,math
from datetime import datetime,timezone
from pathlib import Path

VERSION='routing-20261015.1'
class KnowledgeError(Exception):pass

def load(path, mode='draft'):
    try:
        raw=Path(path).read_bytes();data=json.loads(raw)
    except (OSError,ValueError) as e:raise KnowledgeError('KNOWLEDGE_UNAVAILABLE') from e
    if data.get('schema')!=1 or not isinstance(data.get('entries'),list) or not data['entries']:raise KnowledgeError('KNOWLEDGE_SCHEMA_INVALID')
    try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(data['observed_at'])).total_seconds()
    except (KeyError,ValueError,TypeError):raise KnowledgeError('KNOWLEDGE_TIMESTAMP_INVALID')
    if age>7*86400 or age < -300:raise KnowledgeError('KNOWLEDGE_STALE')
    valid=[];bad=[];ids=set();blocked=list(data.get('blocked_ids',[]))
    for row in data['entries']:
        if not isinstance(row,dict) or not all(isinstance(row.get(k),str) and row[k].strip() for k in ['id','intent','answer','source']):
            bad.append('INVALID_ROW')
            if isinstance(row,dict) and isinstance(row.get('id'),str):blocked.append(row['id'])
            continue
        if row['id'] in ids:raise KnowledgeError('KNOWLEDGE_DUPLICATE_ID')
        ids.add(row['id'])
        if row.get('approved') is True or (mode=='draft' and row.get('draft_review') is True):valid.append(row)
    if not valid:raise KnowledgeError('KNOWLEDGE_NO_ELIGIBLE_ROWS')
    return {'entries':valid,'bad_rows':bad,'blocked_ids':blocked,'version':data['version'],'hash':hashlib.sha256(raw).hexdigest()}

def norm(text):return re.sub(r'\s+',' ',str(text).lower().replace('ё','е')).strip()
PATTERNS={
'greeting':r'^(здравствуйте|добрый день|добрый вечер|привет)[!.,\s]*$|хочу занят|начать обуч',
'price_request':r'сколько сто|стоимост|цен[ауы]|прайс|тариф',
'schedule':r'расписан|свободн.{0,12}мест|когда.{0,12}занят|дни.{0,8}занят|время неудоб|удобн.{0,10}время',
'trial_offer':r'запи[шс].{0,18}пробн|пробн.{0,12}занят|пробный урок',
'after_trial':r'как прошло|диагностик|какие баллы|результат.{0,15}пробн',
'teacher_match':r'молодой учител|только к нему|сменить.{0,10}педагог|поменять.{0,12}преподав|выбрать.{0,12}учител',
'stronger_group':r'слишком легко|сильн.{0,10}групп|уровень групп|нужны индивидуальн',
'mixed_format':r'один урок|очно и онлайн|день.{0,12}формат|сколько.{0,12}очно',
'payment_status':r'я оплат|мы оплат|оплатил|оплатила|деньги пришли|провер.{0,10}оплат|за кого счет',
'payment_link_request':r'пришлите.{0,10}(ссылк|счет)|ссылк.{0,10}оплат|счет на оплат',
'invoice_calculation':r'почему дороже|не весь месяц|разбивк|расчет.{0,10}период|доплат',
'installment_balance':r'рассроч|сколько осталось|можно позже|остаток.{0,12}платеж',
'arranged_payment':r'оплачу.{0,15}(завтра|офис|позже)|договор.{0,12}оплат',
'refund_or_balance':r'вернит|возврат|вернуть деньги|перенесите остаток|остаток.{0,12}перенести',
'missed_lesson':r'простуд|забол|боле[еюлт]|болезн|не прид[её]м|не сможет.{0,12}прийти|пропуст|пропуск|выздоров|вернул.{0,10}после болез',
'provider_cancelled':r'пришли.{0,10}урока нет|школа отмен|педагог отмен',
'shortened_lesson':r'урок короче|сократили урок|один ученик|сокращен.{0,10}урок',
'contract_visit':r'подписать|готов.{0,10}договор|через ребенка|оформ.{0,8}договор',
'contract_error':r'неверные даты|ошибк.{0,12}договор|договор.{0,12}ошиб',
'tax_deduction':r'справк|налогов|вычет',
'maternity_capital':r'маткапитал|материнск',
'form_problem':r'не открывает|уже заполн|нет почты|анкет|форма.{0,10}(ошиб|работ)',
'schedule_correction':r'писали другое время|друг.{0,8}расписан|противореч.{0,10}расписан',
'wrong_link':r'чужую групп|неверн.{0,8}ссылк|ссылк.{0,12}учебн',
'room_conflict':r'ребенок ждет|никого нет|кабинет|опаздыва',
'office_payment':r'до скольких.{0,8}работ|час.{0,10}офис|адрес|где находит|как добрат',
'course_mix_change':r'остаемся только|отказ.{0,10}предмет|закончил.{0,15}напомин|убрать.{0,12}предмет',
'homework_parent_notice':r'не сдает дз|домашн.{0,12}задан|почему не сообщ',
'parent_at_trial':r'можно присутств|родител.{0,12}пробн|пробн.{0,12}родител',
'unsupported_subject':r'есть биолог|есть хим|предмет.{0,10}не вед',
'career_test':r'куда поступ|профориентац|выбрать профиль',
'objections':r'дорого|подумаем|сомнева|пока не готов',
'lead_followup':r'молчание после предложения|повторное касание',
'review_request':r'нам понрав|хочу оставить отзыв|очень понрав',
'bot_question':r'вы бот|ты бот|вы робот|виртуальн.{0,12}администратор',
'senior_delay':r'обещали ответ|ответ.{0,8}задерж|жду ответ',
'human_takeover':r'хочу человека|жив.{0,8}оператор|позовите.{0,12}администратор|соедините.{0,12}человек',
'privacy_request':r'баланс другого|чуж.{0,10}(данн|документ)|паспорт|игнорируй правила',
}
HUMAN={'refund_or_balance','provider_cancelled','shortened_lesson','contract_error','maternity_capital','privacy_request','human_takeover'}
FACTS={'schedule','mixed_format','payment_status','payment_link_request','invoice_calculation','installment_balance','arranged_payment','after_trial','teacher_match','stronger_group','contract_visit','tax_deduction','form_problem','schedule_correction','wrong_link','office_payment','course_mix_change','homework_parent_notice','parent_at_trial','unsupported_subject','senior_delay','trial_offer','missed_lesson','lead_followup'}

STOP=set('как какой какая какие когда где что это есть можно хочу надо нам вас вам нас для про при или еще уже пока будет будет всего меня ребенка ребёнок занятие занятия сегодня завтра очень пожалуйста здравствуйте добрый день вечер спасибо'.split())
def terms(text):
    return {w[:5] if len(w)>5 else w for w in re.findall(r'[а-яa-z]+',norm(text)) if len(w)>2 and w not in STOP}
def lexical_candidates(text,entries):
    query=terms(text)
    docs={e['id']:terms(' '.join([e['intent'],*e.get('examples',[])])) for e in entries if e['id'] not in {'greeting','unknown_answer','crm_unavailable','human_takeover'}}
    weights={w:math.log(1+len(docs)/max(1,sum(w in d for d in docs.values()))) for w in query}
    result=[]
    for sid,words in docs.items():
        hits=query & words
        evidence=sum(weights[w] for w in hits)
        if hits and evidence>=1.5:
            result.append((min(.69,.5+evidence*.025),sid))
    return sorted(result,reverse=True)

def route(text,release,context=None,attachment=False,human_active=False):
    context=context or {};t=norm(text)
    t=re.sub(r'забалел|заболл','заболел',t)
    result={'scenario':None,'reason_code':'KNOWLEDGE_GAP','draft':None,'score':0.0,'score_kind':'deterministic_lexical_evidence_not_probability','sources':[],'dependencies':[],'candidates':[],'version':VERSION}
    if human_active:return dict(result,reason_code='HUMAN_ACTIVE')
    if attachment and not t:return dict(result,reason_code='ATTACHMENT_REVIEW')
    byid={r['id']:r for r in release['entries']}
    probe=re.sub(r'не\s+забол\w*|не\s+боле\w*','',t)
    for sid in release.get('blocked_ids',[]):
        if sid in PATTERNS and re.search(PATTERNS[sid],probe):return dict(result,scenario=sid,reason_code='KNOWLEDGE_ROW_INVALID')
    ranks=[]
    for sid,pattern in PATTERNS.items():
        if sid not in byid:continue
        if sid=='human_takeover' and re.search(r'не хочу человека|не нужен оператор',t):continue
        hits=list(re.finditer(pattern,probe))
        exact=any(t==norm(x) for x in byid[sid].get('examples',[]) if x)
        value=1.0 if exact else min(.96,.8+len(hits)*.04) if hits else 0
        if value:ranks.append((value,sid))
    # Explicit critical signals are routing facts, never business rule approvals.
    forced=None
    if re.search(r'потерялся|ребенок пропал|травм|угрож|небезопас',t):forced=('human_takeover','SAFETY_RISK')
    elif re.search(r'жалоб|недовол|возмут|спор.{0,10}оплат',t):forced=('human_takeover','COMPLAINT')
    elif re.search(PATTERNS['human_takeover'],t) and not re.search(r'не хочу человека|не нужен оператор',t):forced=('human_takeover','EXPLICIT_HUMAN_REQUEST')
    if forced:ranks=[(1.,forced[0])]+[(v,k) for v,k in ranks if k!=forced[0]]
    else:ranks.sort(reverse=True)
    # Bare '+' requires previous inbound context; never invent invoice intent.
    if t=='+':
        previous=context.get('previous_text','')
        if re.search(r'счет|ссылк.{0,10}оплат',norm(previous)):ranks=[(.8,'payment_link_request')]
    weak=False
    if not ranks:
        ranks=lexical_candidates(t,release['entries']);weak=bool(ranks)
    if (not ranks or weak) and context.get('previous_text') and re.search(r'^(а |и |да[.! ]|нет[.! ]|групп|индивидуаль|онлайн|очно|[0-9]{1,2} класс)',t):
        prior=route(context['previous_text'],release)
        if prior.get('scenario') in byid:ranks=[(.7,prior['scenario'])];weak=False
    if not ranks:return dict(result,reason_code='ATTACHMENT_REVIEW') if attachment else result
    result['candidates']=[{'id':sid,'score':value} for value,sid in ranks[:5]]
    score,sid=ranks[0];entry=byid[sid]
    selected=[k for v,k in ranks if k!='greeting']
    if sid=='greeting' and selected:sid=selected[0];entry=byid[sid]
    result.update(scenario=sid,score=score,sources=[entry['source']],dependencies=[entry.get('dependencies','')],next_step=entry.get('next_step',''))
    if forced:reason=forced[1]
    elif sid in HUMAN:reason='MANDATORY_HANDOFF'
    elif weak:reason='SCENARIO_CLARIFICATION'
    elif len(selected)>1 and abs(ranks[0][0]-ranks[1][0])<.08 and not ({sid,selected[1]} <= {'price_request','objections'}):reason='MULTI_INTENT_CLARIFICATION'
    elif sid in FACTS:reason='MISSING_CRM_FACTS'
    else:reason='MISSING_CUSTOMER_DATA' if sid in {'greeting','price_request','career_test','objections'} else 'SCENARIO_READY'
    answer=entry['answer']
    if sid=='missed_lesson':answer='Уточните, пожалуйста, на какие даты и по какому предмету планируется пропуск или возвращение. Для отметки отсутствия нужна проверка администратора; условия отработки и перерасчёта зависят от договора.'
    elif re.search(r'\[[^\]]+\]',answer):answer='Для проверки уточните, пожалуйста: '+entry.get('required_data','предмет и формат')+'. Точные данные необходимо сверить с администратором.'
    if reason=='MULTI_INTENT_CLARIFICATION':answer='Вижу несколько вопросов. Уточните, пожалуйста, какой из них нужно решить в первую очередь?'
    if reason=='SCENARIO_CLARIFICATION':answer='Правильно ли я понимаю, ваш вопрос — '+entry['intent'].lower()+'? Для проверки уточните: '+entry.get('required_data','предмет и формат')+'.'
    if reason=='EXPLICIT_HUMAN_REQUEST':answer=None
    if attachment and not forced:reason='ATTACHMENT_REVIEW';result['dependencies'].append('attachment_not_read')
    return dict(result,reason_code=reason,draft=answer,required_data=entry.get('required_data',''),needs_action=reason in {'MISSING_CRM_FACTS','MANDATORY_HANDOFF','SAFETY_RISK','COMPLAINT','EXPLICIT_HUMAN_REQUEST','ATTACHMENT_REVIEW'})

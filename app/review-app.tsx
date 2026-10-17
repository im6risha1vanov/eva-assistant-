'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3, FileJson, Flag, History, Lightbulb, LockKeyhole, MessageCircle, MessageSquareText, Plus, Search, Settings2, ShieldCheck, Sparkles, Upload, X } from 'lucide-react';
import { contextStats, datasetSchema, emptyWorkspace, nextAdminResponse, type Dataset, type Principle, type Review, type Settings, type Verdict, type Workspace } from '../lib/model';
import demoRaw from '../lib/demo.json';
import { effectiveAnalysis } from '../lib/developer';

const demo = datasetSchema.parse(demoRaw);
type WorkspaceResponse = { workspace: Workspace; revision: number; error?: string };
const labels: Record<Verdict, string> = { good: 'Ответ подходит', lost_context: 'Упущен контекст', wrong_rule: 'Неверное правило', unneeded_question: 'Лишний вопрос', wrong_tone: 'Не тот тон', human_needed: 'Нужен человек' };
const time = (at: string) => new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(at));
const date = (at: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'Europe/Moscow' }).format(new Date(at));
const saveFile = (name: string, value: unknown) => { const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1500); };

export default function ReviewApp({ displayName, canDevelop = false }: { displayName: string; canDevelop?: boolean }) {
  const [workspace, setWorkspace] = useState<Workspace>(emptyWorkspace);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [tab, setTab] = useState<'dialogues' | 'principles' | 'data'>('dialogues');
  const [selected, setSelected] = useState('demo-1');
  const [anchorId, setAnchorId] = useState('');
  const [search, setSearch] = useState('');
  const [topic, setTopic] = useState('Все темы');
  const [onlyUnreviewed, setOnlyUnreviewed] = useState(false);
  const [showFuture, setShowFuture] = useState(true);
  const [highlightContext, setHighlightContext] = useState(false);
  const [note, setNote] = useState('');
  const [draftVerdict, setDraftVerdict] = useState<Verdict>('lost_context');
  const [mobileDetail, setMobileDetail] = useState(false);
  const [modal, setModal] = useState(false);
  const [newRule, setNewRule] = useState({ title: '', text: '', topic: 'Все темы' });
  const [pendingImport, setPendingImport] = useState<Dataset | null>(null);
  const [prefs, setPrefs] = useState<Settings>(emptyWorkspace().settings);
  const importRef = useRef<HTMLInputElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const mutationLock = useRef(false);
  const pack = useMemo(() => { const source = workspace.dataset ?? demo; return { ...source, dialogues: source.dialogues.map(d => ({ ...d, analyses: d.messages.filter(m => m.role === 'client').flatMap(m => { const value = effectiveAnalysis(workspace, d, m.id); return value ? [value] : []; }) })) }; }, [workspace]);
  const isDemo = !workspace.dataset || pack.source.is_demo;
  const topics = Array.from(new Set(pack.dialogues.map(d => d.topic)));
  const datasetId = workspace.dataset_id;
  const currentReviews = workspace.reviews.filter(r => r.dataset_id === datasetId);
  const totalAnswers = pack.dialogues.reduce((n, d) => n + d.analyses.length, 0);
  const reviewedCount = currentReviews.filter(r => pack.dialogues.some(d => d.id === r.dialogue_id && d.analyses.some(a => a.client_message_id === r.message_id))).length;
  const filtered = useMemo(() => pack.dialogues.filter(d => {
    const haystack = [d.title, d.customer_label, d.summary, ...d.messages.map(m => m.text)].join(' ').toLowerCase();
    const unreviewed = !d.analyses.length || d.analyses.some(a => !workspace.reviews.some(r => r.dataset_id === datasetId && r.dialogue_id === d.id && r.message_id === a.client_message_id));
    return (!search || haystack.includes(search.toLowerCase())) && (topic === 'Все темы' || d.topic === topic) && (!onlyUnreviewed || unreviewed);
  }), [pack, search, topic, onlyUnreviewed, workspace.reviews, datasetId]);
  const d = pack.dialogues.find(x => x.id === selected) ?? pack.dialogues[0];
  const clientMessages = d.messages.filter(m => m.role === 'client');
  const anchor = clientMessages.find(m => m.id === anchorId) ?? d.messages.find(m => m.id === d.analyses[0]?.client_message_id) ?? clientMessages[clientMessages.length - 1];
  const a = effectiveAnalysis(workspace, d, anchor?.id ?? '');
  const anchorIndex = d.messages.findIndex(m => m.id === anchor?.id);
  const replies = nextAdminResponse(d, anchor?.id ?? '');
  const stats = contextStats(d, a);
  const review = currentReviews.find(r => r.dialogue_id === d.id && r.message_id === anchor?.id);

  const notify = (value: string) => setToast(value);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    let cancelled = false;
    fetch('/api/workspace', { cache: 'no-store' }).then(async res => { const body = await res.json() as WorkspaceResponse; if (!res.ok) throw new Error(body.error); return body; }).then(body => {
      if (cancelled) return; setWorkspace(body.workspace); setRevision(body.revision); setPrefs(body.workspace.settings);
    }).catch(e => { if (!cancelled) setError(e.message || 'Не удалось загрузить рабочее пространство.'); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => { if (!pack.dialogues.some(x => x.id === selected)) { setSelected(pack.dialogues[0].id); setAnchorId(''); } }, [pack, selected]);
  useEffect(() => { setNote(review?.note ?? ''); setDraftVerdict(review?.verdict ?? 'lost_context'); }, [selected, anchor?.id, review?.note, review?.verdict]);
  useEffect(() => {
    const container = historyRef.current;
    const el = container?.querySelector<HTMLElement>('[data-selected="true"]');
    if (container && el) container.scrollTo({ top: Math.max(0, el.offsetTop - container.clientHeight * 0.32), behavior: 'smooth' });
  }, [selected, anchor?.id, tab, loading]);

  async function mutate(action: string, payload: unknown): Promise<boolean> {
    if (mutationLock.current) return false;
    mutationLock.current = true; setBusy(true); setError('');
    try {
      const res = await fetch('/api/workspace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision, action, payload }) });
      const body = await res.json() as WorkspaceResponse; if (!res.ok) throw new Error(body.error ?? 'Не удалось сохранить.');
      setWorkspace(body.workspace); setRevision(body.revision); return true;
    } catch (e) { setError(e instanceof Error ? e.message : 'Ошибка сохранения.'); return false; }
    finally { mutationLock.current = false; setBusy(false); }
  }
  function selectDialogue(id: string) { setSelected(id); setAnchorId(''); setMobileDetail(true); setHighlightContext(false); }
  async function mark(verdict: Verdict) {
    if (!anchor || !a) return;
    setDraftVerdict(verdict);
    if (await mutate('review', { dataset_id: datasetId, dialogue_id: d.id, message_id: anchor.id, verdict, note })) notify('Оценка сохранена. Ответ клиенту не отправляется.');
  }
  async function loadFile(file?: File) {
    if (!file) return;
    if (file.size > 3_000_000) { setError('Файл больше 3 МБ. Разделите выгрузку на несколько пакетов.'); return; }
    try {
      const parsed = datasetSchema.safeParse(JSON.parse(await file.text()));
      if (!parsed.success) { const issue = parsed.error.issues[0]; throw new Error(`${issue.path.join('.')}: ${issue.message}`); }
      setPendingImport(parsed.data);
    } catch (e) { setError(e instanceof SyntaxError ? 'Это не JSON-файл. Скачайте образец формата на вкладке «Данные».' : e instanceof Error ? e.message : 'Не удалось прочитать файл.'); }
  }
  async function confirmImport() {
    if (!pendingImport) return;
    if (await mutate('import', pendingImport)) { setSelected(pendingImport.dialogues[0].id); setAnchorId(''); setSearch(''); setTopic('Все темы'); setOnlyUnreviewed(false); setPendingImport(null); setTab('dialogues'); notify('Диалоги загружены. Результаты предыдущих оценок сохранены отдельно.'); }
  }
  async function saveRule() {
    if (!newRule.title.trim() || !newRule.text.trim()) return;
    if (await mutate('principle', { ...newRule, id: crypto.randomUUID(), status: 'proposed' })) { setModal(false); setNewRule({ title: '', text: '', topic: 'Все темы' }); notify('Предложение сохранено. Бот ещё не изменён.'); }
  }
  function exportFeedback() {
    saveFile(`eva-corrections-${new Date().toISOString().slice(0, 10)}.json`, {
      feedback_schema_version: 1, exported_at: new Date().toISOString(), dataset_id: datasetId, demo_dataset: isDemo,
      source: pack.source, constraints: { client_send_mode: 'draft_only', owner_approval_required: true, preferred_model: 'gpt-6-luna', model_connection_verified: false },
      preferences: workspace.settings, proposals: workspace.principles,
      reviews: currentReviews, review_scope: 'Оценки относятся к указанному набору и выбранному моменту, не ко всему диалогу автоматически.',
      application_status: 'not_applied_to_bot', developer_changes: workspace.developer,
    });
  }

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="Ева — главная"><span className="brand-symbol"><span/><span/><span/><span/></span><span>ева<span className="brand-dot">.</span></span></a><span className="brand-separator"/><span className="workspace-label">Пиксель / Кодология <ChevronDown size={13}/></span><div className="topbar-right">{canDevelop && <a className="button small outline" href="/developer"><Settings2 size={14}/> Редактор</a>}<span className="private-label"><LockKeyhole size={13}/> Личный кабинет</span><span className="avatar owner" title={displayName}>В</span></div></header>
    <main>
      <div className="page-heading"><div><div className="eyebrow">КАЧЕСТВО ОБЩЕНИЯ</div><h1>Диалог в контексте<span className="heading-dot">.</span></h1><p>Видеть всю историю. Понимать суть. Улучшать общие правила.</p></div><button className="button primary" onClick={() => importRef.current?.click()} disabled={busy || loading}><Upload size={16}/> Загрузить диалоги</button></div>
      <input ref={importRef} type="file" accept=".json,application/json" hidden onChange={e => { void loadFile(e.target.files?.[0]); e.target.value = ''; }}/>
      <div className="nav-row"><nav aria-label="Разделы"><button className={tab === 'dialogues' ? 'active' : ''} onClick={() => setTab('dialogues')}><MessageSquareText size={16}/> Диалоги <span className="count-badge">{pack.dialogues.length}</span></button><button className={tab === 'principles' ? 'active' : ''} onClick={() => setTab('principles')}><BookOpen size={16}/> Общие принципы {workspace.principles.length > 0 && <span className="count-badge">{workspace.principles.length}</span>}</button><button className={tab === 'data' ? 'active' : ''} onClick={() => setTab('data')}><FileJson size={16}/> Данные и экспорт</button></nav><span className="mode-label"><span/> Только черновики</span></div>
      {error && <div className="error-banner" role="alert"><Flag size={16}/><span>{error}</span><button aria-label="Закрыть ошибку" onClick={() => setError('')}><X size={16}/></button></div>}
      {loading ? <div className="loading-state"><span className="loader"/> Загружаем ваше рабочее пространство…</div> : <>
      {isDemo ? <div className="source-banner"><span className="demo-tag">ДЕМО</span><span>Учебные диалоги, не переписка из CRM. <strong>Попробуйте разбор, затем загрузите свою историю.</strong></span><button onClick={() => setTab('data')}>Как подключить <ArrowRight size={14}/></button></div> : <div className="source-banner live"><span className="live-dot"/><span><strong>{pack.source.label}</strong> · срез {date(pack.source.exported_at)}, {time(pack.source.exported_at)} МСК</span><button onClick={() => setTab('data')}>Охват выгрузки <ArrowRight size={14}/></button></div>}
      {tab === 'dialogues' && <div className={`workbench ${mobileDetail ? 'mobile-detail' : ''}`}>
        <aside className="dialogue-sidebar"><div className="sidebar-heading"><span>Входящие на разбор</span><span>{filtered.length}</span></div><label className="search-field"><Search size={15}/><input aria-label="Поиск по всей переписке" value={search} onChange={e => setSearch(e.target.value)} placeholder="Поиск по всей переписке"/></label><div className="list-filters"><select aria-label="Тема диалогов" value={topic} onChange={e => setTopic(e.target.value)}><option>Все темы</option>{topics.map(t => <option key={t}>{t}</option>)}</select><button className={onlyUnreviewed ? 'filter-on' : ''} onClick={() => setOnlyUnreviewed(!onlyUnreviewed)} title="Только без оценки"><Settings2 size={14}/>{onlyUnreviewed ? 'Новые' : 'Все'}</button></div><div className="dialogue-list">{filtered.length === 0 ? <div className="empty-small">Ничего не найдено.<button onClick={() => { setSearch(''); setTopic('Все темы'); setOnlyUnreviewed(false); }}>Сбросить фильтры</button></div> : filtered.map((item, i) => {
          const done = item.analyses.length > 0 && item.analyses.every(an => currentReviews.some(r => r.dialogue_id === item.id && r.message_id === an.client_message_id));
          return <button key={item.id} className={`dialogue-item ${d.id === item.id ? 'selected' : ''}`} onClick={() => selectDialogue(item.id)}><div className="dialogue-person"><span className={`avatar color-${i % 4}`}>{item.customer_label[0]}</span><strong>{item.customer_label}</strong><span className="list-time">{time(item.messages[item.messages.length - 1].at)}</span></div><div className="dialogue-title">{item.title}</div><p>{item.messages.filter(m => m.role === 'client').slice(-1)[0]?.text || item.messages[0].text}</p><div className="dialogue-meta"><span className="topic-chip">{item.topic}</span><span className="channel-label">{item.channel}</span>{done ? <CheckCircle2 size={14} className="done-icon"/> : <span className="unread-dot"/>}</div></button>;
        })}</div><div className="sidebar-progress"><div><span>Ответов оценено</span><strong>{reviewedCount} / {totalAnswers}</strong></div><div className="progress-track"><span style={{ width: `${totalAnswers ? reviewedCount / totalAnswers * 100 : 0}%` }}/></div><p>Одна корректировка может стать правилом для похожих случаев.</p></div></aside>
        <section className="history-panel"><div className="history-header"><button className="back-mobile icon-button" aria-label="К списку диалогов" onClick={() => setMobileDetail(false)}><ArrowLeft size={18}/></button><span className="avatar color-0 large">{d.customer_label[0]}</span><div><h2>{d.customer_label}</h2><p>{d.channel} <span>·</span> {d.branch}</p></div>{d.crm_url && <a className="icon-button" href={d.crm_url} target="_blank" rel="noreferrer" title="Открыть CRM"><ArrowUpRight size={17}/></a>}</div><div className="context-summary"><span className="section-kicker"><History size={13}/> ПРЕДЫСТОРИЯ</span><p>{d.summary || 'Резюме не передано. Полную доступную переписку смотрите ниже.'}</p><span className={`history-coverage ${d.history_complete ? '' : 'partial'}`}><span/>{d.history_complete ? 'Полнота отмечена в выгрузке' : 'История неполная'}</span><span className="coverage-help" title={d.history_note}><CircleHelp size={12}/></span></div><div className="history-controls"><span>{d.messages.length} сообщений <span className="muted">· время МСК</span></span><label><input type="checkbox" checked={showFuture} onChange={e => setShowFuture(e.target.checked)}/> После выбранного момента</label></div>
          <div className="history-scroll" ref={historyRef}>{d.messages.map((m, i) => {
            const future = anchorIndex >= 0 && i > anchorIndex; if (future && !showFuture) return null;
            const active = m.id === anchor?.id;
            const included = highlightContext && a?.used_message_ids?.includes(m.id);
            const newDay = i === 0 || date(m.at) !== date(d.messages[i - 1].at);
            return <div key={m.id} className={`message-wrap ${future ? 'future' : ''}`} data-selected={active}>
              {newDay && <div className="day-divider"><span>{date(m.at)}</span></div>}
              {future && i === anchorIndex + 1 && <div className="future-divider"><Clock3 size={12}/> Далее — переписка после момента оценки</div>}
              <div className={`message-row ${m.role} ${active ? 'message-selected' : ''} ${included ? 'context-included' : ''}`}>
                <div className="message-author">{m.role === 'client' ? 'Клиент' : m.role === 'admin' ? 'Администратор' : 'Событие'}<span>{time(m.at)}</span>{active && <span className="selected-label">РАЗБИРАЕМ</span>}</div>
                {m.role === 'client' ? <button className="message-bubble" onClick={() => { setAnchorId(m.id); setHighlightContext(false); }} title="Разобрать ответ на это сообщение"><span>{m.text || 'Сообщение без текста'}</span>{m.attachments?.map((att, ix) => <span className="attachment" key={ix}>↳ {att.name} · {att.type}</span>)}</button> : <div className="message-bubble"><span>{m.text || 'Сообщение без текста'}</span>{m.attachments?.map((att, ix) => <span className="attachment" key={ix}>↳ {att.name} · {att.type}</span>)}</div>}
                {active && <div className="anchor-caption"><CornerArrow/> Ева должна учитывать сообщения выше</div>}
              </div>
            </div>;
          })}</div><div className="history-footer"><MessageCircle size={14}/> Нажмите на сообщение клиента, чтобы выбрать момент ответа.</div>
        </section>
        <aside className="analysis-panel"><div className="analysis-heading"><div className="eva-mark"><Sparkles size={17}/></div><div><h2>Как ответила бы Ева</h2><p>{isDemo ? 'Учебный вариант · не отправляется' : 'Разбор из загруженного пакета'}</p></div></div>
          <div className="analysis-scroll">{!anchor ? <div className="empty-analysis">В этом диалоге нет сообщения клиента для сравнения.</div> : !a ? <div className="empty-analysis"><CircleHelp size={28}/><h3>Для этого момента нет разбора</h3><p>История доступна, но вариант Евы ещё не загружен. Выберите другое сообщение или добавьте результат анализа из проекта.</p>{canDevelop && <a className="button small outline" href={`/developer?dialogue=${encodeURIComponent(d.id)}&message=${encodeURIComponent(anchor.id)}`}>Создать вариант ответа</a>}<div className="moment-buttons">{d.analyses.map(an => <button key={an.client_message_id} onClick={() => setAnchorId(an.client_message_id)}>Разбор в {time(d.messages.find(m => m.id === an.client_message_id)!.at)} <ArrowRight size={13}/></button>)}</div></div> : <>
            <div className="intent-card"><span className="section-kicker">СУТЬ ОБРАЩЕНИЯ</span><p>{a.intent}</p></div>
            <div className="context-meter"><span className="context-meter-icon"><History size={15}/></span><div><strong>{stats.used === null ? 'Контекст модели не указан' : `${stats.used} из ${stats.preceding} сообщений до ответа`}</strong><span>{stats.used === null ? 'В выгрузке нет списка прочитанных сообщений' : 'Состав контекста указан в выгрузке'}</span></div>{a.used_message_ids && <button onClick={() => setHighlightContext(!highlightContext)} className={highlightContext ? 'active' : ''}>{highlightContext ? 'Скрыть' : 'Показать'}</button>}</div>
            <div className="response-block actual"><div className="response-heading"><span className="admin-mark">А</span><strong>Что ответил администратор</strong><span>ФАКТ</span></div>{replies.length ? replies.map(m => <p key={m.id}>{m.text || 'Ответ без текста'}</p>) : <p className="muted">Ответ сотрудника после этого сообщения отсутствует в выгрузке.</p>}</div>
            <div className="response-block suggested"><div className="response-heading"><Sparkles size={14}/><strong>Вариант Евы</strong><span>ЧЕРНОВИК</span></div><p>{a.draft || 'Черновик не подготовлен. Смотрите причины ниже.'}</p>{canDevelop && anchor && <a className="text-link" href={`/developer?dialogue=${encodeURIComponent(d.id)}&message=${encodeURIComponent(anchor.id)}`}>Редактировать ответ и промт <Settings2 size={13}/></a>}<div className="draft-footer"><ShieldCheck size={12}/><span>{a.model || 'Модель не указана'} · отправки клиенту нет</span></div></div>
            <details className="analysis-details" open><summary><span>На что опирается ответ</span><ChevronDown size={14}/></summary><div className="detail-body">{a.known_facts.length > 0 && <div className="fact-list">{a.known_facts.map((fact, ix) => <div key={ix}><Check size={13}/><span>{fact}</span></div>)}</div>}{a.missing_facts.length > 0 && <div className="missing-facts"><span className="mini-label">ЕЩЁ НЕ ПОДТВЕРЖДЕНО</span>{a.missing_facts.map((fact, ix) => <p key={ix}>{fact}</p>)}</div>}{a.required_actions.length > 0 && <div className="required-actions"><span className="mini-label">НУЖНОЕ ДЕЙСТВИЕ</span>{a.required_actions.map((action, ix) => <p key={ix}>{action}</p>)}</div>}{a.rule_refs.map((rule, ix) => <div className="rule-reference" key={ix}><BookOpen size={13}/><div><strong>{rule.title}</strong><span>{rule.source}</span><em>{rule.status === 'verified' ? 'Помечено проверенным источником' : rule.status === 'proposed' ? 'Предложение, не утверждённое правило' : 'Статус источника неизвестен'}</em></div></div>)}{a.explanation && <p className="explanation">{a.explanation}</p>}</div></details>
            <div className="feedback-section"><div className="feedback-heading"><h3>Суть понята верно?</h3>{review && <span><Check size={12}/> Сохранено</span>}</div><p>Можно просто выбрать оценку — переписывать ответ не нужно.</p><div className="verdict-grid">{(Object.keys(labels) as Verdict[]).map(v => <button key={v} disabled={busy} className={`${review?.verdict === v ? 'chosen' : ''} ${v === 'good' ? 'good-verdict' : ''}`} onClick={() => void mark(v)}>{v === 'good' ? <Check size={13}/> : v === 'lost_context' ? <History size={13}/> : v === 'human_needed' ? <MessageCircle size={13}/> : <Flag size={13}/>} {labels[v]}</button>)}</div><textarea aria-label="Необязательный комментарий к оценке" value={note} onChange={e => setNote(e.target.value)} placeholder="Комментарий — только если хочется пояснить" maxLength={3000}/>{note !== (review?.note ?? '') && <button className="button small outline" disabled={busy} onClick={() => void mark(draftVerdict)}>Сохранить комментарий</button>}<button className="generalize-button" onClick={() => { setNewRule({ title: '', text: '', topic: d.topic }); setModal(true); }}><Lightbulb size={15}/> Задать правило для похожих случаев <ArrowRight size={14}/></button></div>
          </>}</div></aside>
      </div>}

      {tab === 'principles' && <section className="principles-page"><div className="section-intro"><div><span className="eyebrow">КОРРЕКТИРОВКИ В ЦЕЛОМ</span><h2>Один принцип — много диалогов</h2><p>Задайте общие ориентиры. Они попадут в пакет для Codex, а не в каждый отдельный ответ.</p></div><button className="button primary" onClick={() => { setNewRule({ title: '', text: '', topic: 'Все темы' }); setModal(true); }}><Plus size={16}/> Добавить принцип</button></div><div className="guardrail-strip"><ShieldCheck size={17}/><span><strong>Уже решено:</strong> черновики администратору · дополнения после вашего согласования · предпочтение GPT-6 Luna, подключение требует проверки.</span></div><div className="principles-layout"><div className="preferences-card"><h3>Как Ева должна общаться?</h3><p className="muted">Общие вопросы, на которые достаточно ответить один раз.</p>
        <Preference title="Тон разговора" description="Как обращаться к родителям и ученикам?" value={prefs.tone} onChange={value => setPrefs({ ...prefs, tone: value as Settings['tone'] })} options={[['unset','Пока не определено'],['warm','Тепло и по делу, на «вы»'],['formal','Строго официально'],['casual','Живо и неформально']]}/>
        <Preference title="Если не хватает сведений" description="Суть понятна, но для ответа нужны дополнительные данные." value={prefs.clarification} onChange={value => setPrefs({ ...prefs, clarification: value as Settings['clarification'] })} options={[['unset','Пока не определено'],['targeted','Один-два точных вопроса'],['handoff','Указать администратору, чего не хватает']]}/>
        <Preference title="Длина ответа" description="Без потери смысла и важных условий." value={prefs.length} onChange={value => setPrefs({ ...prefs, length: value as Settings['length'] })} options={[['unset','Пока не определено'],['short','Коротко: 1–3 предложения'],['balanced','По ситуации, без лишнего'],['detailed','Подробно объяснять следующие шаги']]}/>
        <Preference title="Родитель сообщает о болезни" description="Изменение записи и финансовые условия всё равно требуют подтверждённых правил." value={prefs.illness} onChange={value => setPrefs({ ...prefs, illness: value as Settings['illness'] })} options={[['unset','Нужно уточнить регламент'],['acknowledge','В черновике поблагодарить, без лишних вопросов'],['admin_action','Показать администратору нужное действие']]}/>
        <Preference title="Уведомления в VK" description="Это предпочтение; действующие уведомления пока не меняются." value={prefs.notifications} onChange={value => setPrefs({ ...prefs, notifications: value as Settings['notifications'] })} options={[['unset','Пока не определено'],['digest','Обычные черновики — в сводку'],['important','Сразу только требующие действия'],['all','Показывать каждый черновик']]}/>
        <button className="button primary" disabled={busy || JSON.stringify(prefs) === JSON.stringify(workspace.settings)} onClick={async () => { if (await mutate('settings', prefs)) notify('Предпочтения сохранены. Передайте экспорт Codex, чтобы подготовить изменения бота.'); }}><Check size={15}/> Сохранить ориентиры</button><p className="footnote">Сохранение на сайте не меняет сценарии бота автоматически.</p></div><div className="proposals-column"><h3>Предложения к регламенту <span>{workspace.principles.length}</span></h3>{workspace.principles.length === 0 ? <div className="proposal-empty"><div className="large-icon"><Lightbulb size={26}/></div><h3>Не нужно править каждый ответ</h3><p>Например: «Не спрашивать возраст и направление повторно, если они уже есть в переписке».</p><button className="button outline" onClick={() => { setNewRule({ title: 'Не повторять известные вопросы', text: 'Перед уточнением проверять предыдущую переписку. Не спрашивать возраст, направление и формат повторно, если они уже известны и не изменились.', topic: 'Все темы' }); setModal(true); }}>Добавить этот пример <Plus size={14}/></button></div> : workspace.principles.map(rule => <article className="proposal-card" key={rule.id}><div><span className="topic-chip">{rule.topic}</span><span className={`proposal-status ${rule.status}`}>{rule.status === 'approved' ? 'Согласовано вами' : 'На согласовании'}</span></div><h3>{rule.title}</h3><p>{rule.text}</p><div className="proposal-actions">{rule.status === 'proposed' && <button disabled={busy} onClick={async () => { if (await mutate('principle', { ...rule, status: 'approved' })) notify('Согласование сохранено. В работающем боте правило ещё не применено.'); }}><Check size={14}/> Согласовать</button>}<button disabled={busy} onClick={() => void mutate('delete_principle', rule.id)}>Удалить предложение</button></div><small>Изменение бота выполняется отдельно через Codex.</small></article>)}</div></div></section>}

      {tab === 'data' && <section className="data-page"><div className="section-intro"><div><span className="eyebrow">ИСТОРИЯ И СВЯЗЬ С ПРОЕКТОМ</span><h2>Ваши диалоги, ваши корректировки</h2><p>Загрузите историю вместе с результатами LLM-разбора. Оценки и принципы сохраняются в вашем закрытом кабинете.</p></div></div><div className="data-grid"><article className="data-card"><div className="large-icon"><Upload size={24}/></div><h3>Загрузить реальные диалоги</h3><p>JSON-выгрузка из Евы, AlfaCRM или Wazzup, приведённая к формату панели. Импортируются история, ответ сотрудника, вариант модели и источники.</p><button className="button primary" onClick={() => importRef.current?.click()} disabled={busy}><Upload size={15}/> Выбрать JSON</button><a className="text-link" href="/dialogues-example.json" download>Скачать образец формата <ArrowDownToLine size={14}/></a><p className="footnote">До 3 МБ, 300 диалогов и 600 сообщений в каждом пакете. Новый пакет заменяет отображаемый; оценки прежних пакетов остаются отдельно.</p></article><article className="data-card"><div className="large-icon"><ArrowDownToLine size={24}/></div><h3>Передать корректировки Codex</h3><p>Один файл с оценками, общими предпочтениями, предложениями и вашим согласованием. Без полного массива клиентских переписок.</p><button className="button outline" onClick={exportFeedback}><ArrowDownToLine size={15}/> Экспортировать корректировки</button><div className="export-summary"><span>{currentReviews.length} оценок</span><span>{workspace.principles.length} принципов</span><span>{workspace.principles.filter(p => p.status === 'approved').length} согласовано</span></div><p className="footnote">Экспорт не применяет изменения и не отправляет сообщения клиентам.</p></article><article className="data-card wide"><div className="data-status-heading"><div><h3>Что подключено сейчас</h3><p>Панель не имеет прямого доступа к вашей CRM и не вызывает LLM самостоятельно.</p></div><span className="status-outline">{isDemo ? 'Учебные данные' : 'Импортированная история'}</span></div><div className="source-details"><div><span>Источник</span><strong>{pack.source.label}</strong></div><div><span>Охват</span><strong>{pack.source.coverage_note}</strong></div><div><span>История в пакете</span><strong>{pack.dialogues.length} диалогов · {pack.dialogues.reduce((sum, item) => sum + item.messages.length, 0)} сообщений · {totalAnswers} разборов</strong></div><div><span>Неполные истории</span><strong>{pack.dialogues.filter(item => !item.history_complete).length} · полнота указана источником, не доказана панелью</strong></div></div><div className="integration-note"><BookOpen size={19}/><div><h4>Подключение через ваш проект</h4><p>Передайте Codex задание ниже. Он должен выгрузить доступную историю и получить варианты ответа на основе регламента — только из сообщений до выбранного момента.</p><a href="/EVA_REVIEW_PANEL_EXPORT_PROMPT.md" download className="text-link">Скачать задание для Codex <ArrowDownToLine size={14}/></a></div></div></article></div></section>}
      </>}
    </main><footer className="app-footer"><span>Ева · пространство разбора</span><span><LockKeyhole size={11}/> Только для владельца · сообщения клиентам не отправляются</span></footer>
    {toast && <div className="toast" role="status"><CheckCircle2 size={18}/>{toast}<button aria-label="Закрыть уведомление" onClick={() => setToast('')}><X size={14}/></button></div>}
    {modal && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget) setModal(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="rule-title"><div className="modal-heading"><div><span className="eyebrow">ОБЩАЯ КОРРЕКТИРОВКА</span><h2 id="rule-title">Правило для похожих случаев</h2></div><button className="icon-button" onClick={() => setModal(false)} aria-label="Закрыть"><X size={20}/></button></div><p>Опишите один принцип. Не нужно переписывать весь ответ.</p><label>Короткое название<input autoFocus maxLength={300} value={newRule.title} onChange={e => setNewRule({ ...newRule, title: e.target.value })} placeholder="Например: не переспрашивать известное"/></label><label>Как следует действовать<textarea rows={4} maxLength={3000} value={newRule.text} onChange={e => setNewRule({ ...newRule, text: e.target.value })} placeholder="Перед уточнением проверять историю диалога…"/></label><label>Для каких случаев<select value={newRule.topic} onChange={e => setNewRule({ ...newRule, topic: e.target.value })}><option>Все темы</option>{topics.map(t => <option key={t}>{t}</option>)}</select></label><div className="modal-note"><ShieldCheck size={16}/> Сначала предложение, затем ваше согласование. Бот автоматически не меняется.</div><button className="button primary full" disabled={busy || !newRule.title.trim() || !newRule.text.trim()} onClick={() => void saveRule()}>Сохранить предложение <ArrowRight size={15}/></button></section></div>}
    {pendingImport && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title"><div className="modal-heading"><h2 id="import-title">Загрузить этот пакет?</h2><button className="icon-button" aria-label="Отменить импорт" onClick={() => setPendingImport(null)}><X size={18}/></button></div><p><strong>{pendingImport.source.label}</strong></p><div className="import-counts"><span>{pendingImport.dialogues.length}<small>диалогов</small></span><span>{pendingImport.dialogues.reduce((sum, item) => sum + item.messages.length, 0)}<small>сообщений</small></span><span>{pendingImport.dialogues.reduce((sum, item) => sum + item.analyses.length, 0)}<small>разборов</small></span></div><p>{pendingImport.source.coverage_note}</p><div className="modal-note">Новый пакет заменит отображаемую историю. Общие принципы и оценки предыдущих пакетов сохранятся отдельно.</div><button className="button primary full" disabled={busy} onClick={() => void confirmImport()}>Подтвердить загрузку <Upload size={16}/></button></section></div>}
  </div>;
}

function Preference({ title, description, value, onChange, options }: { title: string; description: string; value: string; onChange: (value: string) => void; options: string[][] }) { return <label className="preference"><strong>{title}</strong><span>{description}</span><select value={value} onChange={e => onChange(e.target.value)}>{options.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>; }
function CornerArrow() { return <span aria-hidden="true">↳</span>; }

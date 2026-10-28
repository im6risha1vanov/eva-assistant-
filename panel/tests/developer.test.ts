import assert from 'node:assert/strict';
import { test } from 'node:test';
import { emptyWorkspace } from '../lib/model.ts';
import { allowedDeveloper, caseContext, contextHash, dataset, developer, effectiveAnalysis, jobPacket, normalizeWorkspace, resultTemplate, validateResult } from '../lib/developer.ts';
import { developerAction } from '../lib/developer-actions.ts';

const newState = () => normalizeWorkspace(emptyWorkspace());
async function jobState() { const s = newState(); await developerAction(s, 'create_job', { scope: 'one', dialogue_id: 'demo-1', message_id: 'm7' }); return s; }
function validResult(s: ReturnType<typeof newState>) { const j = developer(s).jobs[0]; const r = resultTemplate(j); r.rules = []; const a = dataset(s).dialogues[0].analyses[0]; r.replies[0].analysis = structuredClone(a) as typeof r.replies[number]['analysis']; return r; }

test('developer allowlist denies missing and unrelated identities, normalizes email', () => {
  assert.equal(allowedDeveloper(undefined, 'a@example.com'), false);
  assert.equal(allowedDeveloper('a@example.com', undefined), false);
  assert.equal(allowedDeveloper('b@example.com', 'a@example.com'), false);
  assert.equal(allowedDeveloper('A@example.com', ' a@example.com '), true);
});
test('legacy workspace normalizes without losing existing preferences', () => {
  const s = emptyWorkspace(); s.settings.tone = 'warm'; normalizeWorkspace(s);
  assert.equal(developer(s).active_prompt_id, 'initial'); assert.equal(s.settings.tone, 'warm');
});
test('a manual edit preserves source and records original versus replacement', async () => {
  const s = newState(); const original = dataset(s).dialogues[0].analyses[0].draft;
  await developerAction(s, 'edit', { dialogue_id: 'demo-1', message_id: 'm7', after: 'Спасибо, учтём ваше сообщение.', scope: 'all' });
  assert.equal(developer(s).edits[0].before, original); assert.equal(dataset(s).dialogues[0].analyses[0].draft, original);
  assert.equal(effectiveAnalysis(s, dataset(s).dialogues[0], 'm7')?.draft, 'Спасибо, учтём ваше сообщение.');
  assert.equal(effectiveAnalysis(s, dataset(s).dialogues[0], 'm7')?.model, 'Ваша правка');
});
test('task context excludes summary and future replies', async () => {
  const s = await jobState(); const j = developer(s).jobs[0]; const packet = await jobPacket(s, j);
  assert.equal(packet.cases[0].messages.length, 7); assert.equal(packet.cases[0].messages.some(m => m.id === 'm8'), false);
  assert.equal('summary' in packet.cases[0], false); assert.equal(packet.next_offset, null);
});
test('all-scope targets every client message, not only existing analyses', async () => {
  const s = newState(); await developerAction(s, 'create_job', { scope: 'all' });
  const expected = dataset(s).dialogues.reduce((n, d) => n + d.messages.filter(m => m.role === 'client').length, 0);
  assert.equal(developer(s).jobs[0].targets.length, expected);
});
test('topic-scoped edit examples do not leak into other topic cases', async () => {
  const s = newState(); await developerAction(s, 'edit', { dialogue_id: 'demo-1', message_id: 'm7', after: 'Исправление для темы', scope: 'topic' });
  const d = dataset(s).dialogues.find(d => d.topic !== dataset(s).dialogues[0].topic)!;
  assert.equal(caseContext(s, { dialogue_id: d.id, message_id: d.messages.find(m => m.role === 'client')!.id }).edits.length, 0);
});
test('prompt drafts do not change active configuration, activation invalidates old tasks', async () => {
  const s = await jobState(); const original = await contextHash(s);
  await developerAction(s, 'prompt', { text: 'Новый промт', knowledge: 'Регламент' }); assert.equal(await contextHash(s), original);
  await developerAction(s, 'activate_prompt', developer(s).prompts[1].id);
  await assert.rejects(() => jobPacket(s, developer(s).jobs[0]), /устарело/);
});
test('new edit or approved setting invalidates queued result', async () => {
  const s = await jobState(); const r = validResult(s); s.settings.length = 'short';
  await assert.rejects(() => developerAction(s, 'stage_result', { job_id: r.job_id, result: r }), /устарело/);
});
test('result rejects future context, untracked context and wrong snapshot', async () => {
  const s = await jobState(); const j = developer(s).jobs[0];
  for (const change of ['future', 'empty', 'hash', 'outside', 'duplicate'] as const) {
    const r = validResult(s);
    if (change === 'future') r.replies[0].analysis.used_message_ids!.push('m8');
    if (change === 'empty') r.replies[0].analysis.used_message_ids = [];
    if (change === 'hash') r.context_hash = 'wrong';
    if (change === 'outside') r.replies[0].dialogue_id = 'other';
    if (change === 'duplicate') r.replies.push(structuredClone(r.replies[0]));
    assert.throws(() => validateResult(s, j, r));
  }
});
test('ready result cannot omit target replies', async () => {
  const s = await jobState(); const r = validResult(s); r.replies = [];
  assert.throws(() => validateResult(s, developer(s).jobs[0], r), /все 1/);
});
test('question stage cannot be applied, owner answers invalidate pre-answer result', async () => {
  const s = await jobState(); const r = { ...validResult(s), questions: [{ id: 'scope', text: 'Это правило для всех пропусков?' }], replies: [] };
  await developerAction(s, 'stage_result', { job_id: r.job_id, result: r });
  assert.equal(developer(s).jobs[0].status, 'questions');
  await assert.rejects(() => developerAction(s, 'apply_result', r.job_id));
  await assert.rejects(() => developerAction(s, 'answer', { job_id: r.job_id, answers: {} }));
  await developerAction(s, 'answer', { job_id: r.job_id, answers: { scope: 'Только болезнь' } });
  assert.equal(developer(s).jobs[0].status, 'pending'); assert.equal((await jobPacket(s, developer(s).jobs[0])).answers.scope, 'Только болезнь');
  await assert.rejects(() => developerAction(s, 'stage_result', { job_id: r.job_id, result: r }), /снимку/);
});
test('chat submission stages only, explicit owner application updates previews and approved rules', async () => {
  const s = await jobState(); const r = validResult(s); r.rules = [{ title: 'Учитывать историю', text: 'Не переспрашивать известное.', scope: 'all', topic: '' }];
  r.replies[0].analysis.draft = 'Новый согласованный ответ';
  await developerAction(s, 'stage_result', { job_id: r.job_id, result: r });
  assert.equal(s.principles.length, 0); assert.equal(developer(s).overrides.length, 0);
  await developerAction(s, 'apply_result', r.job_id);
  assert.equal(s.principles[0].status, 'approved'); assert.equal(effectiveAnalysis(s, dataset(s).dialogues[0], 'm7')?.draft, 'Новый согласованный ответ');
  assert.equal(developer(s).jobs[0].status, 'applied');
  await assert.rejects(() => developerAction(s, 'apply_result', r.job_id));
});
test('model cannot self-certify a new business rule', async () => {
  const s = await jobState(); const r = validResult(s);
  const raw = { ...r, replies: [{ ...r.replies[0], analysis: { ...r.replies[0].analysis, rule_refs: [{ title: 'Придумано моделью', source: 'несуществующий документ', status: 'verified' }] } }] };
  assert.equal(validateResult(s, developer(s).jobs[0], raw).replies[0].analysis.rule_refs[0].status, 'proposed');
});

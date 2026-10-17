import { z } from 'zod';
import type { Workspace } from './model.ts';
import { caseContext, contextHash, dataset, developer, editInputSchema, effectiveAnalysis, getPrompt, jobPacket, normalizeWorkspace, promptSchema, validateResult, type Target } from './developer.ts';
const now = () => new Date().toISOString();
const id = z.string().min(1).max(160);
export async function developerAction(state: Workspace, action: string, payload: unknown) {
  normalizeWorkspace(state); const dev = developer(state);
  if (action === 'edit') {
    const input = editInputSchema.parse(payload);
    const d = dataset(state).dialogues.find(d => d.id === input.dialogue_id);
    if (!d || !d.messages.some(m => m.id === input.message_id && m.role === 'client')) throw new Error('Сообщение клиента не найдено.');
    if (dev.edits.length >= 1000) throw new Error('Лимит истории: 1000 правок. Экспортируйте результаты.');
    dev.edits.push({ ...input, id: crypto.randomUUID(), dataset_id: state.dataset_id, before: effectiveAnalysis(state, d, input.message_id)?.draft ?? '', topic: d.topic, at: now() });
  } else if (action === 'prompt') {
    if (dev.prompts.length >= 100) throw new Error('Не более 100 версий промта.');
    dev.prompts.push({ ...promptSchema.parse(payload), id: crypto.randomUUID(), at: now() });
  } else if (action === 'activate_prompt') {
    const pid = id.parse(payload); if (!dev.prompts.some(p => p.id === pid)) throw new Error('Версия не найдена.'); dev.active_prompt_id = pid;
  } else if (action === 'create_job') {
    const input = z.object({ scope: z.enum(['one', 'topic', 'all']), dialogue_id: id.optional(), message_id: id.optional(), topic: z.string().max(300).optional(), instructions: z.string().max(6000).default(''), offset: z.number().int().min(0).default(0) }).parse(payload);
    if (dev.jobs.length >= 40) throw new Error('Сохранено 40 заданий. Экспортируйте и удалите завершённые задания.');
    const targets: Target[] = [];
    for (const d of dataset(state).dialogues) {
      if (input.scope === 'one' && d.id !== input.dialogue_id) continue;
      if (input.scope === 'topic' && d.topic !== input.topic) continue;
      for (const m of d.messages) if (m.role === 'client' && (input.scope !== 'one' || m.id === input.message_id)) targets.push({ dialogue_id: d.id, message_id: m.id });
    }
    const selected: Target[] = []; let contextBytes = 0;
    for (const target of targets.slice(input.offset, input.offset + 250)) {
      const size = new TextEncoder().encode(JSON.stringify(caseContext(state, target))).length;
      if (contextBytes + size > 1_500_000) break;
      contextBytes += size; selected.push(target);
    }
    if (!selected.length) throw new Error('Нет сообщений в диапазоне либо контекст одного случая больше 1,5 МБ. Подготовьте меньшую выгрузку для разбора.');
    const hash = await contextHash(state);
    dev.jobs.push({ id: crypto.randomUUID(), dataset_id: state.dataset_id, source_hash: hash, context_hash: hash, targets: selected, instructions: input.instructions, scope: `${input.scope === 'all' ? 'Все темы' : input.scope === 'topic' ? input.topic : 'Один ответ'} · ${input.offset + 1}–${input.offset + selected.length} из ${targets.length}`, at: now(), status: 'pending', questions: [], answers: {} });
  } else if (action === 'answer') {
    const input = z.object({ job_id: id, answers: z.record(z.string().max(4000)) }).parse(payload);
    const job = dev.jobs.find(j => j.id === input.job_id); if (!job || job.status !== 'questions') throw new Error('Нет открытых вопросов в этом задании.');
    await jobPacket(state, job, 0, 1);
    if (Object.keys(input.answers).some(key => !job.questions.some(q => q.id === key)) || job.questions.some(q => !input.answers[q.id]?.trim())) throw new Error('Ответьте на каждый вопрос задания.');
    job.answers = { ...job.answers, ...input.answers }; job.context_hash = crypto.randomUUID(); job.status = 'pending';
  } else if (action === 'stage_result') {
    const input = z.object({ job_id: id, result: z.unknown() }).parse(payload);
    const job = dev.jobs.find(j => j.id === input.job_id); if (!job) throw new Error('Задание не найдено.');
    await jobPacket(state, job, 0, 1);
    const result = validateResult(state, job, input.result);
    job.answers = Object.fromEntries(Object.entries(job.answers).filter(([key]) => result.questions.some(q => q.id === key && job.questions.some(old => old.id === key && old.text === q.text))));
    job.result = result; job.questions = result.questions; job.status = result.questions.length ? 'questions' : 'ready';
  } else if (action === 'apply_result') {
    const jobId = id.parse(payload); const job = dev.jobs.find(j => j.id === jobId);
    if (!job || job.status !== 'ready' || !job.result || job.result.questions.length) throw new Error('Сначала нужен завершённый разбор без неотвеченных вопросов.');
    await jobPacket(state, job, 0, 1);
    const result = validateResult(state, job, job.result); const timestamp = now();
    if (state.principles.length + result.rules.length > 200) throw new Error('Лимит 200 принципов. Сначала объедините или удалите лишние.');
    const targetKeys = new Set(result.replies.map(r => JSON.stringify([r.dialogue_id, r.analysis.client_message_id])));
    dev.overrides = dev.overrides.filter(o => o.dataset_id !== state.dataset_id || !targetKeys.has(JSON.stringify([o.dialogue_id, o.analysis.client_message_id])));
    for (const r of result.replies) dev.overrides.push({ dataset_id: state.dataset_id, dialogue_id: r.dialogue_id, analysis: { ...r.analysis, model: 'Разбор через чат · согласован владельцем', generated_at: timestamp }, job_id: job.id, at: timestamp });
    for (let index = 0; index < result.rules.length; index++) { const r = result.rules[index]; state.principles.push({ id: `${job.id}-${index}`, title: r.title, text: r.text, topic: r.scope === 'all' ? 'Все темы' : r.topic, status: 'approved', updated_at: timestamp }); }
    if (result.prompt_suggestion && dev.prompts.length < 100) dev.prompts.push({ id: crypto.randomUUID(), text: result.prompt_suggestion, knowledge: getPrompt(state).knowledge, note: `Предложение из задания ${job.id}; ещё не активировано`, at: timestamp });
    job.status = 'applied'; job.applied_at = timestamp;
  } else if (action === 'delete_job') {
    const jobId = id.parse(payload); dev.jobs = dev.jobs.filter(j => j.id !== jobId);
  } else throw new Error('Неизвестное действие.');
}

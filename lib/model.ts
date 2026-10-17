import { z } from 'zod';
import type { DeveloperState } from './developer';
const short = z.string().trim().min(1).max(300);
const id = z.string().trim().min(1).max(160);
export const messageSchema = z.object({
  id, role: z.enum(['client', 'admin', 'system']), text: z.string().max(16000), at: z.string().datetime({ offset: true }),
  attachments: z.array(z.object({ name: short, type: short })).max(20).optional(),
});
export const analysisSchema = z.object({
  client_message_id: id, draft: z.string().max(16000), intent: short, explanation: z.string().max(4000).default(''),
  known_facts: z.array(z.string().max(600)).max(30).default([]), missing_facts: z.array(z.string().max(600)).max(30).default([]),
  required_actions: z.array(z.string().max(600)).max(20).default([]),
  rule_refs: z.array(z.object({ title: short, source: z.string().max(1000), status: z.enum(['verified', 'proposed', 'unknown']) })).max(30).default([]),
  used_message_ids: z.array(id).max(400).optional(), model: z.string().max(160).optional(), generated_at: z.string().datetime({ offset: true }).optional(),
});
export const dialogueSchema = z.object({
  id, customer_label: short, title: short, topic: short, channel: short.default('Не указан'), branch: short.default('Не указан'),
  summary: z.string().max(3000).default(''), history_complete: z.boolean().default(false), history_note: z.string().max(1000).default('Полнота истории не подтверждена источником.'),
  crm_url: z.string().url().refine(value => { const u = new URL(value); return u.protocol === 'https:' && u.hostname === 'kodologiyapiksel.s20.online' && !u.username && !u.password; }, 'Разрешена ссылка только на вашу AlfaCRM.').optional(),
  messages: z.array(messageSchema).min(1).max(600), analyses: z.array(analysisSchema).max(250).default([]),
});
export const datasetSchema = z.object({ schema_version: z.literal(1),
  source: z.object({ label: short, exported_at: z.string().datetime({ offset: true }), coverage_note: z.string().max(2000).default('Охват источника не указан.'), is_demo: z.boolean().default(false) }),
  dialogues: z.array(dialogueSchema).min(1).max(300),
}).superRefine((pack, ctx) => {
  const ids = new Set<string>();
  pack.dialogues.forEach((d, di) => {
    if (ids.has(d.id)) ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'id'], message: 'Повтор ID диалога.' });
    ids.add(d.id);
    const indices = new Map<string, number>();
    d.messages.forEach((m, mi) => {
      if (indices.has(m.id)) ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'messages', mi, 'id'], message: 'Повтор ID сообщения.' });
      if (mi && Date.parse(m.at) < Date.parse(d.messages[mi - 1].at)) ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'messages', mi, 'at'], message: 'Сообщения должны идти в хронологическом порядке.' });
      indices.set(m.id, mi);
    });
    const anchors = new Set<string>();
    d.analyses.forEach((a, ai) => {
      const anchor = indices.get(a.client_message_id);
      if (anchor === undefined || d.messages[anchor]?.role !== 'client') ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'analyses', ai], message: 'Разбор должен относиться к сообщению клиента.' });
      if (anchors.has(a.client_message_id)) ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'analyses', ai], message: 'Повтор разбора одного сообщения.' });
      anchors.add(a.client_message_id);
      for (const used of a.used_message_ids ?? []) {
        const index = indices.get(used);
        if (index === undefined || anchor === undefined || index > anchor) ctx.addIssue({ code: 'custom', path: ['dialogues', di, 'analyses', ai, 'used_message_ids'], message: 'В контексте разбора есть неизвестное или последующее сообщение.' });
      }
    });
  });
});
export type Dataset = z.infer<typeof datasetSchema>;
export type Dialogue = Dataset['dialogues'][number];
export type Analysis = Dialogue['analyses'][number];
export type Message = Dialogue['messages'][number];
export const verdicts = ['good', 'lost_context', 'wrong_rule', 'unneeded_question', 'wrong_tone', 'human_needed'] as const;
export type Verdict = typeof verdicts[number];
export const reviewSchema = z.object({ dataset_id: id, dialogue_id: id, message_id: id, verdict: z.enum(verdicts), note: z.string().max(3000).default('') });
export type Review = z.infer<typeof reviewSchema> & { updated_at: string };
export const principleSchema = z.object({ id, title: short, text: z.string().trim().min(1).max(3000), topic: short, status: z.enum(['proposed', 'approved']).default('proposed') });
export type Principle = z.infer<typeof principleSchema> & { updated_at: string };
export const settingsSchema = z.object({ tone: z.enum(['warm', 'formal', 'casual', 'unset']), clarification: z.enum(['targeted', 'handoff', 'unset']), length: z.enum(['short', 'balanced', 'detailed', 'unset']), illness: z.enum(['acknowledge', 'admin_action', 'unset']), notifications: z.enum(['digest', 'important', 'all', 'unset']) });
export type Settings = z.infer<typeof settingsSchema>;
export type Workspace = { dataset: Dataset | null; dataset_id: string; reviews: Review[]; principles: Principle[]; settings: Settings; developer?: DeveloperState };
export function emptyWorkspace(): Workspace { return { dataset: null, dataset_id: 'demo', reviews: [], principles: [], settings: { tone: 'unset', clarification: 'unset', length: 'unset', illness: 'unset', notifications: 'unset' } }; }
export function reviewKey(datasetId: string, dialogueId: string, messageId: string) { return JSON.stringify([datasetId, dialogueId, messageId]); }
export function nextAdminResponse(d: Dialogue, anchorId: string): Message[] {
  const index = d.messages.findIndex(m => m.id === anchorId); if (index < 0) return [];
  const result: Message[] = [];
  for (const m of d.messages.slice(index + 1)) { if (m.role === 'client') break; if (m.role === 'admin') result.push(m); }
  return result;
}
export function contextStats(d: Dialogue, a: Analysis | undefined) {
  const index = a ? d.messages.findIndex(m => m.id === a.client_message_id) : -1;
  return { preceding: index + 1, used: a?.used_message_ids ? new Set(a.used_message_ids).size : null, historyComplete: d.history_complete };
}

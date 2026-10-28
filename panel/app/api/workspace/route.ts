import { readWorkspace as read, saveWorkspace } from '../../../lib/workspace-store';
import { canDevelop } from '../../developer-access';
import { z } from 'zod';
import { getChatGPTUser } from '../../chatgpt-auth';
import { datasetSchema, emptyWorkspace, principleSchema, reviewSchema, settingsSchema, type Workspace } from '../../../lib/model';
export const dynamic = 'force-dynamic';
const headers = { 'Cache-Control': 'no-store' };
function reply(body: unknown, status = 200) { return Response.json(body, { status, headers }); }
export async function GET() {
  const user = await getChatGPTUser(); if (!user) return reply({ error: 'Войдите в свой аккаунт для доступа.' }, 401);
  try { const current = await read(user.userId); if (!canDevelop(user)) delete current.workspace.developer; return reply(current); } catch { return reply({ error: 'Не удалось загрузить данные. Попробуйте обновить страницу.' }, 503); }
}
export async function POST(request: Request) {
  const user = await getChatGPTUser(); if (!user) return reply({ error: 'Нужен вход в аккаунт.' }, 401);
  if (!canDevelop(user)) return reply({ error: 'Изменения доступны только разработчику.' }, 403);
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return reply({ error: 'Недопустимый источник запроса.' }, 403);
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).length > 3_000_000) return reply({ error: 'Разделите выгрузку на файлы до 3 МБ.' }, 413);
    const body = z.object({ revision: z.number().int().nonnegative(), action: z.enum(['import', 'review', 'principle', 'delete_principle', 'settings']), payload: z.unknown() }).parse(JSON.parse(raw));
    const current = await read(user.userId);
    if (current.revision !== body.revision) return reply({ error: 'Данные изменились в другой вкладке. Обновите страницу и повторите изменение.' }, 409);
    const state = current.workspace; const now = new Date().toISOString();
    if (body.action === 'import') {
      const pack = datasetSchema.parse(body.payload);
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(pack)));
      state.dataset_id = Array.from(new Uint8Array(bytes)).map(x => x.toString(16).padStart(2, '0')).join(''); state.dataset = pack;
    } else if (body.action === 'review') {
      const review = reviewSchema.parse(body.payload);
      if (review.dataset_id !== state.dataset_id) return reply({ error: 'Набор диалогов изменился. Обновите страницу.' }, 409);
      if (state.dataset && !state.dataset.dialogues.some(d => d.id === review.dialogue_id && d.messages.some(m => m.id === review.message_id && m.role === 'client'))) return reply({ error: 'Сообщение не найдено в текущем наборе.' }, 400);
      state.reviews = state.reviews.filter(r => !(r.dataset_id === review.dataset_id && r.dialogue_id === review.dialogue_id && r.message_id === review.message_id)); state.reviews.push({ ...review, updated_at: now });
      if (state.reviews.length > 5000) return reply({ error: 'Лимит оценок достигнут. Экспортируйте результаты перед следующим этапом.' }, 400);
    } else if (body.action === 'principle') {
      const principle = principleSchema.parse(body.payload); state.principles = state.principles.filter(p => p.id !== principle.id); state.principles.push({ ...principle, updated_at: now });
      if (state.principles.length > 200) return reply({ error: 'Не более 200 предложений в рабочем пространстве.' }, 400);
    } else if (body.action === 'delete_principle') { const pid = z.string().max(160).parse(body.payload); state.principles = state.principles.filter(p => p.id !== pid); }
    else state.settings = settingsSchema.parse(body.payload);
    return reply(await saveWorkspace(user.userId, state, body.revision));
  } catch (error) {
    if (error instanceof z.ZodError) return reply({ error: error.issues[0]?.message ?? 'Неверный формат.', path: error.issues[0]?.path.join('.') }, 400);
    if (error instanceof SyntaxError) return reply({ error: 'Файл должен содержать корректный JSON.' }, 400);
    return reply({ error: 'Не удалось сохранить. Изменение не подтверждено; попробуйте ещё раз.' }, 503);
  }
}

import { z } from 'zod';
import { developerUser } from '../../developer-access';
import { readWorkspace, saveWorkspace } from '../../../lib/workspace-store';
import { developerAction } from '../../../lib/developer-actions';
import { developer, jobPacket } from '../../../lib/developer';
export const dynamic = 'force-dynamic';
const reply = (body: unknown, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
export async function GET(request: Request) {
  const user = await developerUser(); if (!user) return reply({ error: 'Доступ только для разработчика.' }, 403);
  try {
    const current = await readWorkspace(user.userId); const url = new URL(request.url); const jobId = url.searchParams.get('job');
    if (!jobId) return reply(current);
    const job = developer(current.workspace).jobs.find(j => j.id === jobId); if (!job) return reply({ error: 'Задание не найдено.' }, 404);
    return reply(await jobPacket(current.workspace, job, 0, 250));
  } catch (e) { return reply({ error: e instanceof Error ? e.message : 'Данные недоступны.' }, 400); }
}
export async function POST(request: Request) {
  const user = await developerUser(); if (!user) return reply({ error: 'Доступ только для разработчика.' }, 403);
  const origin = request.headers.get('origin'); if (origin && origin !== new URL(request.url).origin) return reply({ error: 'Недопустимый источник.' }, 403);
  try {
    const text = await request.text(); if (new TextEncoder().encode(text).length > 4_000_000) return reply({ error: 'Размер запроса больше 4 МБ.' }, 413);
    const body = z.object({ revision: z.number().int().nonnegative(), action: z.string().max(40), payload: z.unknown() }).parse(JSON.parse(text));
    const current = await readWorkspace(user.userId); if (current.revision !== body.revision) return reply({ error: 'Данные изменились в другой вкладке или в чате. Обновите страницу.' }, 409);
    await developerAction(current.workspace, body.action, body.payload);
    return reply(await saveWorkspace(user.userId, current.workspace, current.revision));
  } catch (e) { return reply({ error: e instanceof Error ? e.message : 'Не удалось сохранить.' }, 400); }
}

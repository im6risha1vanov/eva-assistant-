import { env } from 'cloudflare:workers';
import { emptyWorkspace, type Workspace } from './model';
import { normalizeWorkspace } from './developer';
export async function readWorkspace(userId: string) {
  if (!env.DB) throw new Error('Хранилище недоступно.');
  const row = await env.DB.prepare('SELECT payload, revision FROM review_workspaces WHERE user_id = ?').bind(userId).first<{ payload: string; revision: number }>();
  return { workspace: normalizeWorkspace(row ? JSON.parse(row.payload) as Workspace : emptyWorkspace()), revision: row?.revision ?? 0 };
}
export async function saveWorkspace(userId: string, state: Workspace, revision: number) {
  const payload = JSON.stringify(state);
  if (new TextEncoder().encode(payload).length > 8_000_000) throw new Error('Лимит рабочего пространства 8 МБ. Экспортируйте историю и очистите старые завершённые задания.');
  const saved = await env.DB!.prepare('INSERT INTO review_workspaces (user_id, payload, revision, updated_at) VALUES (?, ?, 1, ?) ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, revision = review_workspaces.revision + 1, updated_at = excluded.updated_at WHERE review_workspaces.revision = ? RETURNING revision').bind(userId, payload, new Date().toISOString(), revision).first<{ revision: number }>();
  if (!saved) throw new Error('Конфликт сохранения: обновите страницу и повторите.');
  return { workspace: state, revision: saved.revision };
}

import { env } from 'cloudflare:workers';
import { getChatGPTUser, type ChatGPTUser } from './chatgpt-auth';
import { allowedDeveloper } from '../lib/developer';
export function canDevelop(user: ChatGPTUser | null) { return allowedDeveloper(user?.email, env.EVA_DEVELOPER_EMAILS); }
export async function developerUser() { const user = await getChatGPTUser(); return canDevelop(user) ? user : null; }

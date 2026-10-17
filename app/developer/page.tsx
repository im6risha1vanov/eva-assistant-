import { requireChatGPTUser } from '../chatgpt-auth';
import { canDevelop } from '../developer-access';
import DeveloperApp from './developer-app';
export const dynamic = 'force-dynamic';
export default async function Page() { const user = await requireChatGPTUser('/developer'); if (!canDevelop(user)) return <main><h1>Доступ только для разработчика</h1><p>Ссылка не заменяет вход в разрешённый аккаунт.</p><a href="/">К диалогам</a></main>; return <DeveloperApp displayName={user.displayName}/>; }

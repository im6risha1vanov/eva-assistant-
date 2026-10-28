import { requireChatGPTUser } from './chatgpt-auth';
import ReviewApp from './review-app';
import { canDevelop } from './developer-access';
export const dynamic = 'force-dynamic';
export default async function Page() { const user = await requireChatGPTUser('/'); return <ReviewApp displayName={user.displayName} canDevelop={canDevelop(user)} />; }

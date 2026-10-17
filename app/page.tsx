import { requireChatGPTUser } from './chatgpt-auth';
import ReviewApp from './review-app';
export const dynamic = 'force-dynamic';
export default async function Page() { const user = await requireChatGPTUser('/'); return <ReviewApp displayName={user.displayName} />; }

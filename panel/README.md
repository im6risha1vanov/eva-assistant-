# Ева — диалог в контексте

Owner-private Sites/Vinext app. Client/admin history and imported LLM drafts at a selected point in a conversation. Context provenance, future-message boundaries, quick ratings, general preferences and explicit approval of proposed rules. No customer-sending tools or CRM credentials. No LLM calls are made by this application.

## Storage and access

ChatGPT identity required on the page and every API operation. D1 workspace rows are keyed by authenticated user ID. Writes use revision checks plus atomic optimistic concurrency. Runtime does not create tables. SQL migrations are generated from db/schema.ts and applied by Sites.

Imported dialogues are private user data. Demo conversations are invented and are not school policy. The application records source claims of coverage; it cannot independently prove the upstream export is complete. Analysis context IDs are validated against the selected client-message boundary. Future replies are available to the reviewer but cannot be listed as model input in an import.

## Integration

The initial data path is JSON import, documented in public/EVA_REVIEW_PANEL_EXPORT_PROMPT.md. Data is validated with Zod and bounded to 3 MB / 300 dialogues / 600 messages per dialogue. A new dataset replaces the displayed history; reviews of previous dataset versions remain stored separately. Feedback export contains current-dataset ratings and global proposals/preferences, not full message history. Bot updates are never automatic.

## Verification

Run `node --experimental-strip-types tests/model.test.ts` and `node node_modules/typescript/bin/tsc --noEmit`. Build through the Sites skill. Browser QA is skipped in managed environments without the control-browser skill.

## Developer workshop (v2)

`/developer` provides reply editing with immutable before/after history, scope selection (one message / topic / all uploaded conversations), versioned prompts and a regulation text, clarification questions and staged result previews. The imported client/admin history is never rewritten. Only an explicit developer approval updates panel previews and approved principles. Production bots, Wazzup and CRM are not modified.

This version deliberately uses **the current ChatGPT conversation**, not an LLM API. No API key or external model dependency exists. Site MCP at `/mcp` exposes `eva_list_tasks`, paginated `eva_get_task`, and `eva_submit_result`. Sites provisions authentication and the personal plugin. Install/connect that plugin via Plugins → Personal → Created by you, then ask the chat to analyze the latest task. Installing is separate from publication. File export/import is also available; no simulated analysis or automatic background calls occur.

Every data-bearing MCP call and every developer REST call requires a signed-in identity whose email is in the server-only `EVA_DEVELOPER_EMAILS` allowlist. The Site remains owner-private. Sharing the URL alone does not grant access. Missing configuration denies developer access. Per-user D1 rows and optimistic concurrency are preserved. Discovery has no private data; MCP does not expose approval or production-sending tools.

Jobs contain at most 250 client anchors, bounded to 1.5 MB of contextual cases. Large selections require subsequent ranges; the stored task displays its exact range and count. All client messages can be targeted, even those without an existing LLM analysis. Model context contains only chronological messages up to each client anchor; dialogue summaries and future administrator replies are excluded. Other-case edits are behavior examples, not facts about the current customer. `used_message_ids` must include the anchor and cannot contain unknown/future IDs. A ready result must cover every target. New self-certified rule references are downgraded to proposals.

Context fingerprints invalidate jobs after dataset, active prompt, edits, principles or preferences change. Answering clarification questions issues a new result token so a pre-answer result cannot be applied. New prompt drafts remain inactive until explicit activation; chat prompt suggestions become inactive versions after result approval. MCP only stages results. Workspace writes are bounded to 8 MB; imports remain 3 MB, chat results 4 MB. History export is available before cleanup.

Additional verification: `node --experimental-strip-types tests/developer.test.ts`.

# Ева — диалог в контексте

Owner-private Sites/Vinext app. Client/admin history and imported LLM drafts at a selected point in a conversation. Context provenance, future-message boundaries, quick ratings, general preferences and explicit approval of proposed rules. No customer-sending tools or CRM credentials. No LLM calls are made by this application.

## Storage and access

ChatGPT identity required on the page and every API operation. D1 workspace rows are keyed by authenticated user ID. Writes use revision checks plus atomic optimistic concurrency. Runtime does not create tables. SQL migrations are generated from db/schema.ts and applied by Sites.

Imported dialogues are private user data. Demo conversations are invented and are not school policy. The application records source claims of coverage; it cannot independently prove the upstream export is complete. Analysis context IDs are validated against the selected client-message boundary. Future replies are available to the reviewer but cannot be listed as model input in an import.

## Integration

The initial data path is JSON import, documented in public/EVA_REVIEW_PANEL_EXPORT_PROMPT.md. Data is validated with Zod and bounded to 3 MB / 300 dialogues / 600 messages per dialogue. A new dataset replaces the displayed history; reviews of previous dataset versions remain stored separately. Feedback export contains current-dataset ratings and global proposals/preferences, not full message history. Bot updates are never automatic.

## Verification

Run `node --experimental-strip-types tests/model.test.ts` and `node node_modules/typescript/bin/tsc --noEmit`. Build through the Sites skill. Browser QA is skipped in managed environments without the control-browser skill.

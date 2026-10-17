import { integer, sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const reviewWorkspaces = sqliteTable('review_workspaces', {
  userId: text('user_id').primaryKey(), payload: text('payload').notNull(),
  revision: integer('revision').notNull().default(0), updatedAt: text('updated_at').notNull(),
});

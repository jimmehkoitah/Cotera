import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
export const games = sqliteTable('games', {id:text('id').primaryKey(), version:integer('version').notNull(), data:text('data').notNull()});
export const attempts = sqliteTable('attempts', {id:text('id').primaryKey(), count:integer('count').notNull(), expires:integer('expires').notNull()});

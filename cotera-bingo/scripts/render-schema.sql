-- Same two tables as drizzle/0000_eminent_tyger_tiger.sql, safe to re-run on every boot.
CREATE TABLE IF NOT EXISTS `attempts` (
	`id` text PRIMARY KEY NOT NULL,
	`count` integer NOT NULL,
	`expires` integer NOT NULL
);
CREATE TABLE IF NOT EXISTS `games` (
	`id` text PRIMARY KEY NOT NULL,
	`version` integer NOT NULL,
	`data` text NOT NULL
);
-- Matches from finished rounds, one row per round, so the live game row stays small.
CREATE TABLE IF NOT EXISTS `match_log` (
	`id` text PRIMARY KEY NOT NULL,
	`mode` text NOT NULL,
	`data` text NOT NULL
);

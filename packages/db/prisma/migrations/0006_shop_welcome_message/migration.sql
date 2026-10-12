-- The greeting a shop's assistant opens with (Telegram /start, the web chat
-- and the site widget). Null means the built-in greeting.
ALTER TABLE shops ADD COLUMN IF NOT EXISTS "welcomeMessage" TEXT;

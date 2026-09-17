# integration (telegram-bot)

Reserved for tests that exercise more than one module of the bot together
(e.g. a Telegram update handler against a stubbed `@zify/db` and agent HTTP
call). Empty for now — `src/index.ts` is a single file with no exported
handlers yet; add tests here as it gets broken up.

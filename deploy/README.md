# استقرار زایفای با pyinfra

این پوشه کل فرایند استقرار Zify را نگه می‌دارد. Zify یک monorepo با سه سرویس
است: پنل ادمین (Next.js، در `apps/admin`)، ایجنت (FastAPI/LangGraph روی
Python، در `apps/agent`) و ربات تلگرام (`apps/telegram-bot`)، به‌علاوه یک
دیتابیس PostgreSQL با اکستنشن pgvector (`packages/db`). روی سرور به Node.js،
Bun، uv (برای پایتون)، PostgreSQL و pm2 (برای اجرای هر سه سرویس) نیاز است؛
nginx فقط پنل ادمین را reverse-proxy می‌کند.

**این همان سروری است که `valida` هم رویش است**: `181.41.194.141` (کاربر
`root`، پورت ۲۲) — یک سرور مشترک با چند سایت که nginx با vhost های نام‌دار
(نه `default_server`) بینشان تفکیک می‌کند.

## پیش‌نیازها (فقط یک‌بار، روی ماشین شما)

```bash
python -m pip install -r deploy/requirements.txt
cp deploy/deploy_secrets.example.py deploy/deploy_secrets.py
# بعد مقادیر واقعی (OpenAI، sms.ir، توکن تلگرام، ...) رو توش بذارید
```

## اولین اجرا

اگر همین ماشین قبلاً valida را روی همین سرور دیپلوی کرده، کلید SSH شما احتمالاً
از قبل روی سرور نصب است و رمزی پرسیده نمی‌شود:

```bash
python -m pyinfra deploy/inventory.py deploy/deploy.py
```

در غیر این صورت (اولین اتصال از این ماشین):

```bash
python -m pyinfra deploy/inventory.py deploy/deploy.py --ssh-password-prompt
```

همین اجرا کلید عمومی SSH شما را روی سرور نصب می‌کند (اگر نبود)، PostgreSQL و
pgvector و Node.js و Bun و uv و pm2 را نصب می‌کند، یک دیتابیس و رمز عبور
تصادفی برایش می‌سازد، هر سه اپ را می‌سازد، migrate/seed می‌کند و با pm2 بالا
می‌آورد.

## اجراهای بعدی

```bash
npm run deploy
```

که معادل اجرای همین pyinfra است. برای دیدن تغییرات بدون اعمال شدنشان:

```bash
python -m pyinfra deploy/inventory.py deploy/deploy.py --dry --diff
```

## این استقرار چه کاری می‌کند

۰. **آماده‌سازی (پیش‌پرواز)** — نسخه‌های قدیمی که دیگر سرو نمی‌شوند پاک
   می‌شوند (نسخهٔ در حال استقرار و آنچه `current` به آن اشاره می‌کند هرگز پاک
   نمی‌شوند) و بعد فضای آزاد دیسک چک می‌شود؛ چون این سرور را با valida (و
   احتمالاً پروژه‌های دیگر) مشترک هستید، دیسک اهمیت بیشتری دارد — هر نسخه هم
   `node_modules` کامل دارد هم یک venv پایتون کامل (`uv sync` برای ایجنت).
۱. **پایهٔ سیستم** — بسته‌های پایه، Node.js (شبکهٔ اطمینان — اپ‌ها روی Bun
   اجرا می‌شوند، نه Node)، Bun، uv، pm2، تنظیم تایم‌زون روی `Asia/Tehran` و
   افزودن کلید عمومی SSH شما.
۲. **دیتابیس** — نصب PostgreSQL با apt (نه Docker) به‌علاوه بستهٔ
   `postgresql-<نسخه>-pgvector` متناظر (نسخهٔ Postgres نصب‌شده را خودش تشخیص
   می‌دهد، چون ممکن است این سرور از قبل نسخه‌ای دیگر برای valida داشته
   باشد). در اولین اجرا یک رمز عبور و یک JWT secret تصادفی ساخته و در
   `/var/www/zify/shared/.env` ذخیره می‌شود — **یک فایل مشترک برای هر سه
   سرویس**، دقیقاً مثل `.env` ریشهٔ ریپو در توسعهٔ محلی (به
   `apps/admin/next.config.ts`، `apps/agent/main.py` و
   `apps/telegram-bot/package.json` نگاه کنید — هر سه همین یک فایل را پیدا
   می‌کنند). این فایل بین نسخه‌ها مشترک است و با هر دیپلوی از نو ساخته
   نمی‌شود. اکستنشن `vector` هم با یوزر سوپریوزر ساخته می‌شود (پکیج pgvector
   لزوماً trusted نیست).
۳. **سایت** — تمام فایل‌های ردیابی‌شده توسط git در یک tar.gz بسته‌بندی و
   آپلود می‌شود؛ نامش از هش محتوا ساخته می‌شود، پس اگر چیزی عوض نشده باشد هیچ
   آپلود/بیلدی دوباره انجام نمی‌شود. روی سرور در
   `/var/www/zify/releases/<شناسهٔ نسخه>/` باز می‌شود، `.env` مشترک به ریشه و
   به `packages/db` لینک می‌شود (Prisma CLI کنار schema خودش هم `.env`
   می‌خواهد) و بعد: `bun install` → (در `apps/agent`) `uv sync` → (در
   `packages/db`) `prisma generate` (هم کلاینت JS هم کلاینت پایتون —
   دومی به venv تازه‌ساز نیاز دارد، برای همین `uv sync` قبلش می‌آید) →
   `prisma migrate deploy` → (در `apps/admin`) `bun run build` → `prisma db
   seed`. فقط بعد از موفقیت همهٔ این مراحل (یک فایل نشانه‌ی `.build-complete`
   نوشته می‌شود) لینک `/var/www/zify/current` به این نسخه سوییچ می‌کند.
۴. **سرویس‌ها (pm2)** — `ecosystem.config.cjs` (در ریشهٔ ریپو، از قبل commit
   شده) هر سه اپ را تعریف می‌کند. هر دیپلوی `pm2 startOrReload` را مستقیماً
   روی مسیر واقعی نسخهٔ تازه اجرا می‌کند (نه از طریق symlink `current`، تا
   ابهامی در اینکه pm2 کدام نسخه را resolve می‌کند نباشد) و `pm2 save` را
   می‌زند تا بعد از ری‌استارت سرور هم برگردد.
۵. **nginx** — فقط پنل ادمین را reverse-proxy می‌کند (صفحات و `/api/**`) به
   `127.0.0.1:3010`؛ ایجنت و ربات به‌صورت عمومی expose نمی‌شوند. `_next/static/`
   مستقیم از دیسک سرو می‌شود.
۶. **HTTPS** (اختیاری) و **فایروال** (اختیاری) — پایین‌تر توضیح داده شده‌اند.

## ساختار پوشه

| مسیر | کار |
| --- | --- |
| `inventory.py` | تعریف سرور (همان سرور valida) و پارامترهای اتصال SSH |
| `ssh_config` | keepalive و timeout اتصال SSH |
| `group_data/production.py` | تنظیمات قابل تغییر (دامنه، پورت‌ها، مدل OpenAI، ...) |
| `deploy_secrets.py` | **گیت‌ایگنور شده** — کلیدهای واقعی (OpenAI، sms.ir، توکن تلگرام، ادمین) |
| `deploy_secrets.example.py` | نمونهٔ `deploy_secrets.py` برای کپی کردن |
| `deploy.py` | نقطهٔ شروع؛ تسک‌ها را به ترتیب صدا می‌زند |
| `tasks/system.py` | بسته‌های پایه، Node.js، Bun، uv، pm2، تایم‌زون، کلید SSH، فایروال |
| `tasks/database.py` | نصب PostgreSQL+pgvector و ساخت `.env` مشترک |
| `tasks/website.py` | بسته‌بندی سورس، آپلود، build هر سه سرویس، سوییچ `current` |
| `tasks/service.py` | اجرا/ری‌لود سه اپ با pm2 |
| `tasks/nginx.py` | کانفیگ nginx (فقط پنل ادمین) و گواهی HTTPS |
| `templates/zify.conf.j2` | قالب کانفیگ nginx (ری‌ورس‌پروکسی) |
| `templates/setup-env.sh.j2` | اسکریپت idempotent ساخت `.env` + نقش/دیتابیس/اکستنشن Postgres |
| `templates/ensure-postgres.sh.j2` | بالا آوردن واقعی کلاستر Postgres |
| `templates/prepare-release.sh.j2` | هرس نسخه‌های قدیمی و توقف دیپلوی وقتی دیسک جا ندارد |
| `.artifacts/` | آرشیوهای ساخته‌شدهٔ محلی (در git نادیده گرفته می‌شود) |

## تنظیمات

اکثرش در `group_data/production.py`:

- `site_domain` — تا وقتی `None` باشد سایت روی هیچ نامی جواب نمی‌دهد (چون این
  یک vhost نام‌دار است، نه `default_server` — با valida و بقیهٔ سایت‌های این
  سرور سر آدرس IP خام رقابت نمی‌کند). بعد از اینکه DNS دامنه را به این سرور
  وصل کردید، مقدارش را بگذارید.
- `letsencrypt_email` — با ست شدن همزمان این و `site_domain`، استقرار بعدی
  certbot را نصب و گواهی HTTPS را با ریدایرکت خودکار فعال می‌کند.
- `configure_firewall` — با `True` شدن ufw فعال می‌شود. چون این سرور مشترک
  است، قبل از روشن کردنش مطمئن شوید چیز دیگری روی این سرور به پورتی غیر از
  SSH/80/443 نیاز ندارد.
- `keep_releases` / `min_free_disk_mb` — مثل valida، با این تفاوت که پیش‌فرض
  دیسک بالاتر است (۴۰۰۰ مگابایت) چون هر نسخه یک venv پایتون کامل هم دارد.
- `app_port` (۳۰۱۰) — پورت پنل ادمین. **این مقدار در `ecosystem.config.cjs`
  هم hardcode شده** — عوض کردنش اینجا به‌تنهایی کافی نیست.
- `agent_port` (۳۰۱۱) — پورت ایجنت؛ این یکی واقعاً از `.env` خوانده می‌شود
  (`apps/agent/main.py`)، پس عوض کردنش اینجا کافی است.
- `db_name` / `db_user` — مطابق `docker-compose.yml` توسعهٔ محلی: `zify_db` /
  `zify`.
- `openai_base_url` / `openai_chat_model` / `openai_embedding_model` —
  می‌توانید به یک gateway سازگار با OpenAI اشاره کنید (مثل توسعهٔ محلی).
- `deepseek_base_url` / `deepseek_chat_model` و `gemini_base_url` /
  `gemini_embedding_model` — سرویس‌های دوم برای failover: وقتی سرویس اول جواب
  ندهد ایجنت خودکار سراغ این‌ها می‌رود. با همان `openai_api_key` کار می‌کنند.
  خالی گذاشتن هر base URL یعنی برای آن نوع فراخوانی failover نباشد.
- `langsmith_tracing` / `langsmith_endpoint` / `langsmith_project` —
  تریسینگ LangSmith؛ کلید واقعی در `deploy_secrets.py`.
- `langfuse_host` — فقط وقتی کلیدهای Langfuse (`deploy_secrets.py`) پر باشند
  فعال می‌شود (`apps/agent/app/tracing.py` خودش opt-in است).
- `sms_mock` — خودکار محاسبه می‌شود: تا وقتی `smsir_api_key` خالی باشد،
  `true` (کد OTP در پاسخ API برمی‌گردد، نه با پیامک واقعی).

### کلیدهای واقعی: `deploy_secrets.py`

**گیت‌ایگنور شده** (هیچ‌وقت commit نمی‌شود). اولین بار:

```bash
cp deploy/deploy_secrets.example.py deploy/deploy_secrets.py
```

مقادیرش (توضیح هرکدام در خود فایل):

- `openai_api_key` — بدونش ایجنت بالا می‌آید ولی هر تماس LLM خطا می‌دهد.
- `langsmith_api_key`, `langfuse_public_key`/`langfuse_secret_key` — اختیاری،
  تریسینگ.
- `smsir_api_key`, `smsir_template_id` — بدونشان `sms_mock` روشن می‌ماند.
- `telegram_bot_token` — توکن از @BotFather.

حساب‌ها (ورود صاحبان فروشگاه و مدیران پلتفرم) دیگر اینجا تنظیم نمی‌شوند: در
`packages/db/prisma/seed-accounts.ts` تعریف شده‌اند و با هر دیپلوی seed می‌شوند.

بدون این فایل، `group_data/production.py` موقع لود شدن خطای روشن می‌دهد.

## همگام‌سازی `.env` با تنظیمات

`/var/www/zify/shared/.env` در اولین دیپلوی ساخته می‌شود و رمزهای
تولیدشده‌اش (`DB_PASSWORD`، `JWT_SECRET`، `DATABASE_URL`) دیگر هیچ‌وقت عوض
نمی‌شوند. اما کلیدهایی که از تنظیمات دیپلوی می‌آیند در **هر** دیپلوی با مقدار
فعلی `group_data/production.py` و `deploy_secrets.py` همگام می‌شوند
(`templates/setup-env.sh.j2`) — فهرست کامل در خود آن فایل. فقط کلیدی که واقعاً
عوض شده بازنویسی می‌شود و در خروجی دیپلوی فقط **نامش** چاپ می‌شود، نه مقدارش.

دقت کنید برعکسش هم صادق است: اگر یکی از این کلیدها را دستی روی سرور عوض کنید،
دیپلوی بعدی آن را به مقدار تنظیمات برمی‌گرداند. تغییر را همیشه در تنظیمات
بدهید.

## بازگشت به نسخهٔ قبل (rollback)

نسخه‌های قبلی روی سرور می‌مانند، پس برگشتن کد فقط عوض کردن symlink است —
**دیتابیس را برنمی‌گرداند**:

```bash
python -m pyinfra deploy/inventory.py exec -- ls -1t /var/www/zify/releases
python -m pyinfra deploy/inventory.py exec -- \
  ln -sfn /var/www/zify/releases/<شناسهٔ نسخه> /var/www/zify/current
python -m pyinfra deploy/inventory.py exec -- \
  bash -c 'cd /var/www/zify/releases/<شناسهٔ نسخه> && pm2 startOrReload ecosystem.config.cjs --update-env'
```

## دستورهای مفید

```bash
# وضعیت هر سه سرویس
python -m pyinfra deploy/inventory.py exec -- pm2 status

# لاگ زنده یک سرویس
python -m pyinfra deploy/inventory.py exec -- pm2 logs zify-admin
python -m pyinfra deploy/inventory.py exec -- pm2 logs zify-agent
python -m pyinfra deploy/inventory.py exec -- pm2 logs zify-bot

# وضعیت nginx / PostgreSQL
python -m pyinfra deploy/inventory.py exec -- systemctl status nginx postgresql

# لاگ خطاهای nginx
python -m pyinfra deploy/inventory.py exec -- tail -n 50 /var/log/nginx/zify.error.log
```

## عیب‌یابی

**`[WinError 10053] An established connection was aborted...`** — همان مشکلی
که در README ولیدا توضیح داده شده: اتصال SSH وسط کار (معمولاً روی مکث تأییدیهٔ
"Detected changes") قطع شده. یا با `-y` اجرا کنید تا مکث پیش نیاید، یا به
keepalive موجود در [ssh_config](ssh_config) تکیه کنید.

اجرای دوباره بعد از یک استقرار نیمه‌کاره کاملاً بی‌خطر است؛ نسخه فقط با دیدن
فایل نشانهٔ `.build-complete` «تمام‌شده» حساب می‌شود.

**بیلد سرور کند است یا کم می‌آورد** — `bun install` + `uv sync`
(langgraph/langchain) + `next build` روی یک VPS کم‌رم می‌تواند کند باشد یا
OOM بخورد؛ حداقل ۲ گیگ رم برایش در نظر بگیرید — بیشتر از valida، چون یک venv
پایتون کامل هم اضافه شده.

## نکته‌ها

- سرور باید دبیان یا اوبونتو باشد (apt و systemd).
- این سرور با valida مشترک است. قبل از تغییر `configure_firewall` یا هر
  چیزی که سطح سیستم را لمس می‌کند، مطمئن شوید روی valida اثر نمی‌گذارد.
- تا وقتی دامنه‌ای ست نشده، Zify روی این سرور از بیرون در دسترس نیست (چون
  vhost نام‌دار است، نه `default_server`) — برای تست محلی از
  `python -m pyinfra deploy/inventory.py exec -- curl -H "Host: <دامنهٔ آینده>" http://localhost:3010`
  یا SSH port-forward استفاده کنید.
- مستندات pyinfra: <https://docs.pyinfra.com/en/3.x/>

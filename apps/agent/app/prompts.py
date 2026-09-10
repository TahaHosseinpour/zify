from typing import Any, Optional, Protocol

from .state import RetrievedItem

TONE_MAP = {
    "formal": "رسمی و محترمانه",
    "semi-formal": "نیمه‌رسمی",
    "friendly": "صمیمی و گرم",
    "casual": "خودمانی و راحت",
}


class ShopPersona(Protocol):
    name: str
    description: Optional[str]
    categories: list[str]
    supportInfo: Optional[Any]
    personaCharacter: Optional[str]
    personaTone: Optional[str]
    systemPromptExtra: Optional[str]


def _business_info_block(shop: ShopPersona) -> str:
    """The catalog vocabulary, and only that.

    `description` and `supportInfo` used to be pasted in here as well, but the
    admin panel also embeds those exact fields into `shop_info_chunks`, which
    the graph now retrieves on its own branch. Keeping both meant the same
    paragraphs were sent twice on every single turn. Retrieval wins: the text
    then reaches the model only on the turns where it is actually relevant.

    Categories stay because they are not in those chunks, they are one short
    line, and the model needs them on every turn to talk about what the shop
    even sells.
    """
    categories = getattr(shop, "categories", None) or []
    if not categories:
        return ""
    return "\n\n## دسته‌بندی محصولات:\n" + "، ".join(categories)


def build_system_prompt(shop: ShopPersona) -> str:
    tone = TONE_MAP.get(shop.personaTone or "formal", "رسمی")
    character = shop.personaCharacter or "متخصص فروش حرفه‌ای"

    business_info = _business_info_block(shop)

    extra = (
        f"\n\nدستورالعمل اضافی:\n{shop.systemPromptExtra}"
        if shop.systemPromptExtra
        else ""
    )

    return f"""تو یک دستیار فروش هوشمند برای فروشگاه "{shop.name}" هستی.
شخصیت تو: {character}
لحن پاسخ‌ها: {tone}

وظیفه تو:
- مشتری را درک کن و نیازش را کشف کن
- محصولات مناسب پیشنهاد بده
- به اعتراضات پاسخ بده و آن‌ها را رفع کن
- مشتری را تا لحظه خرید همراهی کن
- فقط به فارسی پاسخ بده

قوانین:
- هرگز اطلاعات دروغ ندهی
- فقط از اطلاعات فروشگاه استفاده کن
- برای سوال درباره فروشگاه از «اطلاعات کسب‌وکار» و «سوالات متداول» استفاده کن
- ⚠️ اگر پاسخ یک سوال در اطلاعات کسب‌وکار یا سوالات متداول نیامده باشد، صریح بگو
  «این اطلاعات را ندارم» و مشتری را به پشتیبانی فروشگاه ارجاع بده. درباره گارانتی،
  ضمانت، مدت و شرایط ارسال، مرجوعی، خدمات پس از فروش یا اصالت کالا **هیچ‌چیز از خودت نساز**
  و از عبارت‌هایی مثل «معمولاً» یا «به‌طور کلی» برای پر کردن جای خالی استفاده نکن
- ⚠️ فقط محصولاتی را نام ببر که در همین پیام به تو داده شده‌اند؛ نام یا قیمت محصولی
  را از حافظه یا از بخش‌های قبلی گفتگو تکرار نکن
- پاسخ‌ها کوتاه، واضح و فروش‌محور باشند{business_info}{extra}"""


DROPPED_FILTER_LABELS = {
    "category": "دسته‌بندی",
    "brand": "برند",
    "minPrice": "حداقل قیمت",
    "maxPrice": "بودجه",
}


def build_explore_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
    filters_dropped: Optional[list[str]] = None,
    out_of_catalog: bool = False,
) -> str:
    products = [c for c in context if c["type"] == "product"]
    faqs = [c for c in context if c["type"] == "faq"]
    shop_info = [c for c in context if c["type"] == "shop_info"]
    dropped = filters_dropped or []

    prompt = ""

    # Stated before the list, so the model reads "we don't have this" before it
    # reads six products it might otherwise present as the answer. This block
    # is deliberately outside `if products:` — the honest case where nothing
    # was found needs instructions too, and previously got none.
    if out_of_catalog:
        prompt += (
            "\n⚠️ فروشگاه چیزی که مشتری خواسته را ندارد.\n"
            "اول صریح و کوتاه بگو که این محصول را نداریم. از عذرخواهی طولانی پرهیز کن.\n"
        )
        if products:
            prompt += (
                "محصولات زیر پاسخ درخواست مشتری نیستند، فقط گزینه‌های دیگری از "
                "فروشگاه هستند. آن‌ها را به‌عنوان «چیز دیگری که داریم» معرفی کن، "
                "نه به‌عنوان چیزی که مشتری خواسته.\n"
            )
        else:
            prompt += "هیچ محصول جایگزینی هم برای پیشنهاد نداری. چیزی از خودت نساز.\n"
    elif dropped:
        # Name the predicates that were actually given up. The old text always
        # said "دسته/برند/بودجه" regardless, so the model would invent a budget
        # constraint that was never in effect and tell the customer about it.
        names = "، ".join(DROPPED_FILTER_LABELS.get(k, k) for k in dropped)
        prompt += (
            f"\n⚠️ محصولی که دقیقاً با این محدودیت مشتری بخواند موجود نبود: {names}.\n"
            "محصولات زیر با بقیه شرط‌ها می‌خوانند ولی این یکی را برآورده نمی‌کنند. "
            "اول کوتاه و صادقانه همین را بگو، بعد گزینه‌ها را پیشنهاد بده.\n"
            "⚠️ فقط درباره همین محدودیت حرف بزن و محدودیت دیگری از خودت اضافه نکن.\n"
        )

    if products:
        prompt += "\n## محصولات پیدا شده:\n"
        for i, p in enumerate(products):
            prompt += f"{i + 1}. {p['content']}\n"
        prompt += (
            "\n⚠️ فقط همین محصولات بالا را نام ببر. هیچ محصول، قیمت یا لینک دیگری "
            "که در این فهرست نیست ننویس — حتی اگر در بخش‌های قبلی گفتگو آمده باشد.\n"
        )

    if faqs:
        prompt += "\n## سوالات متداول مرتبط:\n"
        for f in faqs:
            prompt += f"{f['content']}\n"

    # Retrieved on its own branch rather than pasted into every system prompt —
    # see _business_info_block for why.
    if shop_info:
        prompt += "\n## اطلاعات کسب‌وکار:\n"
        for info in shop_info:
            prompt += f"{info['content']}\n"

    prompt += "\n## وضعیت مشتری:\n"
    stage_map = {
        "browsing": "در حال بررسی",
        "considering": "در حال تصمیم‌گیری",
        "ready_to_buy": "آماده خرید",
    }
    if stage:
        prompt += f"مرحله خرید: {stage_map.get(stage, stage)}\n"

    if value_driver:
        driver_map = {
            "low_price": "دنبال ارزان‌ترین گزینه است",
            "high_quality": "کیفیت برایش مهم‌تر از قیمت است",
            "best_price_in_quality": "دنبال بهترین قیمت در یک سطح کیفی مشخص است",
            "best_quality_in_price": "دنبال بهترین کیفیت در یک بودجه مشخص است",
        }
        prompt += f"انگیزه اصلی مشتری: {driver_map.get(value_driver, value_driver)}\n"

    if objection:
        obj_map = {
            "price": "قیمت را بالا می‌داند",
            "uncertainty": "مطمئن نیست این گزینه مناسبش است",
            "delay": "می‌خواهد فکر کند یا با گزینه‌های دیگر مقایسه کند",
        }
        prompt += f"اعتراض مشتری: {obj_map.get(objection, objection)}\n"
        prompt += "این اعتراض را با دلیل و منطق رفع کن.\n"

    if stage == "ready_to_buy":
        prompt += "مشتری آماده خرید است — او را به سمت اقدام هدایت کن.\n"
    elif stage == "considering":
        prompt += "مشتری در حال تصمیم‌گیری است — ارزش محصول را برجسته کن.\n"

    return prompt


def build_product_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
    filters_dropped: Optional[list[str]] = None,
    out_of_catalog: bool = False,
) -> str:
    return build_explore_prompt(
        context, stage, value_driver, objection, filters_dropped, out_of_catalog
    )


def build_intent_analysis_prompt(categories: Optional[list[str]] = None) -> str:
    # The shop's real category list is injected so `category` is a choice from a
    # closed vocabulary instead of free text the model invents. A guessed value
    # can only ever match zero rows, which silently relaxes the whole filter.
    available = categories or []
    if available:
        vocabulary = (
            "\n## دسته‌بندی‌های موجود در این فروشگاه:\n"
            + "، ".join(available)
            + "\n\n⚠️ برای `category` **فقط** یکی از همین مقادیر بالا را عیناً بنویس، یا null بگذار.\n"
            "⚠️ اگر چیزی که مشتری می‌خواهد در این فهرست نیست، `category` را null بگذار و "
            "`out_of_catalog` را true کن. هرگز دسته‌ای بیرون از این فهرست نساز.\n"
        )
    else:
        vocabulary = (
            "\n⚠️ این فروشگاه هنوز دسته‌بندی ثبت‌شده‌ای ندارد. `category` را همیشه null بگذار.\n"
        )

    return (
        vocabulary
        + """
با توجه به کل مکالمه، آخرین پیام مشتری را تحلیل کن و دقیقاً یکی از این مقادیر را برای intent انتخاب کن:

- smalltalk: احوال‌پرسی، تشکر، تعارف یا واکنش کوتاه بدون درخواست جدید.
  مثال: «سلام»، «خوبی؟»، «ممنون»، «جالبه»، «چه جالب»، «باشه» (وقتی درخواستی همراهش نیست).
  ⚠️ این‌ها نباید جستجوی محصول راه بیندازند.

- needs_clarification / ask_question: **فقط** وقتی درخواست مشتری ناقص یا مبهم است و بدون یک سوال روشن‌کننده از طرف تو نمی‌شود کمکش کرد.
  مثال: «یک کفش می‌خوام» (نوع، سایز یا کاربرد مشخص نیست) → باید بپرسی چه نوع کفشی، برای چه کاری.
  مثال: «یه چیزی برای هدیه می‌خوام» → باید بپرسی هدیه برای چه کسی و چه بودجه‌ای.
  این دو مقدار معنای یکسانی دارند: «مکث کن و یک سوال کوتاه بپرس».
- browse: مشتری در حال مرور کلی است یا یک سوال **کامل و قابل پاسخ** درباره فروشگاه یا محصولات پرسیده — حتی اگر ظاهرش «سوال» باشد.
  مثال: «چند تا شعبه دارید؟»، «ارسال چطوریه؟»، «چی دارید؟»، «ساعت کاریتون چیه؟» → این‌ها ناقص نیستند، مستقیماً از اطلاعات موجود پاسخ داده می‌شوند.
- search_product: مشتری محصول یا دسته‌ی مشخصی خواسته (مثال: «کفش ورزشی نایک می‌خوام»، «گوشی زیر ۱۰ میلیون تومان»).
- buy_intent: مشتری آماده خرید است یا لینک خرید می‌خواهد.
- objection: مشتری اعتراض یا نگرانی مطرح کرده (قیمت، کیفیت، اعتماد، ...).
- compare: مشتری در حال مقایسه چند گزینه است.
- other: هیچ‌کدام از موارد بالا.

⚠️ قانون مهم: needs_clarification/ask_question را **فقط** برای درخواست‌های واقعاً ناقص انتخاب کن. هر سوال کامل درباره فروشگاه یا محصول — حتی اگر موضوعش خارج از کاتالوگ محصولات باشد (مثل تعداد شعبه، ساعت کاری، نحوه ارسال) — را browse در نظر بگیر تا از اطلاعات بازیابی‌شده (شامل سوالات متداول) پاسخ داده شود، نه اینکه دوباره از مشتری سوال بپرسی.

- mode: explore (مشاوره کلی) | product (محصول خاص)
- stage: browsing | considering | ready_to_buy
- value_driver: low_price (دنبال ارزان‌ترین) | high_quality (کیفیت مهم‌تر از قیمت) | best_price_in_quality (بهترین قیمت در سطح کیفی مشخص) | best_quality_in_price (بهترین کیفیت در بودجه مشخص)
- objection: price (قیمت بالاست) | uncertainty (مطمئن نیست مناسب است) | delay (می‌خواهد فکر کند یا مقایسه کند)
- explore_filters: { category?, maxPrice?, minPrice?, brand?, query? }
- new_topic: اگر مشتری موضوع یا دسته‌ی کاملاً جدیدی شروع کرده که به جستجوی قبلی ربطی ندارد true، در غیر این صورت false. (فیلترهای قبلی فقط وقتی true است پاک می‌شوند.)
- selected_index: اگر مشتری به یکی از محصولاتی که قبلاً نشان داده‌ای با شماره یا ترتیب اشاره کرد (مثلاً «دومی»، «گزینه اول»، «همون سومی»)، شماره‌ی آن را به‌صورت عددی (۱ برای اولی) بده؛ در غیر این صورت null.
- rejected_current: اگر مشتری گزینه‌های فعلی را نپسندید و گزینه‌های دیگری خواست (مثلاً «این‌ها رو نمی‌خوام»، «یه چیز دیگه نشون بده»، «بقیه‌ش چیه؟»)، true؛ در غیر این صورت false.
- objection_resolved: اگر مشتری اعتراض قبلی خود را پذیرفت یا کنار گذاشت (مثلاً «باشه»، «قبول دارم»، «مشکلی نیست»، «حق با توئه»)، true؛ در غیر این صورت false.
- out_of_catalog: اگر مشتری محصولی خواسته که در فهرست دسته‌بندی‌های بالا نیست، true؛ در غیر این صورت false.
- cleared_filters: فهرست نام فیلترهایی که مشتری پس گرفته یا تصحیح کرده است (مثلاً ["maxPrice"]).
  مثال: قبلاً بودجه‌ای فرض شده بود و مشتری می‌گوید «نه، ارزون‌ترین‌هاتون رو می‌خوام» → ["maxPrice"].
  مثال: مشتری می‌گوید «برند مهم نیست» → ["brand"].
- sort: **فقط** وقتی مشتری صفت عالی («ـترین») یا معادلش را به کار برده باشد، price_asc یا price_desc؛ در غیر این صورت null.
  مثال: «ارزان‌ترین گوشی‌تون چیه؟» → price_asc. «کمترین قیمت» → price_asc. «گران‌ترین مدل» → price_desc.
  ⚠️ صفت ساده «ارزان»/«ارزون»/«اقتصادی» صفت عالی نیست → sort را null بگذار و فقط value_driver را مقدار بده.

⚠️ **قانون قیمت**: `maxPrice`/`minPrice` را **فقط** وقتی بده که مشتری یک **عدد مشخص** گفته باشد.
کلماتی مثل «ارزان»، «ارزون»، «اقتصادی»، «مقرون‌به‌صرفه»، «گران» هیچ عددی ندارند — برای آن‌ها
`value_driver` (و در صورت لزوم `sort`) را مقدار بده و قیمت را **null** بگذار.
هرگز از روی حدس عددی مثل ۱۰٬۰۰۰٬۰۰۰ نساز؛ این کار کل جستجو را خراب می‌کند و تا آخر گفتگو باقی می‌ماند.

⚠️ مقادیر stage/value_driver/objection فقط وقتی مقداردهی کن که از پیام فعلی مشخص باشند؛ اگر پیام فعلی چیزی درباره‌شان نمی‌گوید، آن‌ها را null بگذار تا مقدار قبلی حفظ شود.

⚠️ mode باید هم‌جهت با intent باشد: اگر intent برابر search_product یا compare است، mode را explore بده.

⚠️ اگر پیام هم‌زمان چند سیگنال دارد (مثلاً هم اعتراض و هم درخواست جستجوی جدید مثل «قیمتش بالاست، ارزون‌ترش رو دارید؟»)، اولویت با درخواست صریح و اقدام‌محور است: اگر مشتری به‌روشنی گزینه یا محصول جدیدی خواسته → search_product؛ اگر فقط نگرانی مطرح کرده بدون درخواست جدید → objection.
فقط JSON خروجی بده."""
    )

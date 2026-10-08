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
    categories = [str(c)[:CATEGORY_NAME_LIMIT] for c in (getattr(shop, "categories", None) or [])]
    if not categories:
        return ""
    return "\n\n## دسته‌بندی محصولات:\n" + "، ".join(categories[:CATEGORY_LIST_LIMIT])


# The persona fields are free text the shop owner types, and the system prompt
# is resent on every turn of every conversation. Bounding them here is part of
# what makes a turn's cost bounded (see graph.REPLY_MAX_TOKENS).
PERSONA_CHARACTER_LIMIT = 200
PROMPT_EXTRA_LIMIT = 600
CATEGORY_LIST_LIMIT = 40
CATEGORY_NAME_LIMIT = 40


def build_system_prompt(shop: ShopPersona) -> str:
    tone = TONE_MAP.get(shop.personaTone or "formal", "رسمی")
    character = (shop.personaCharacter or "متخصص فروش حرفه‌ای")[:PERSONA_CHARACTER_LIMIT]

    business_info = _business_info_block(shop)

    extra = (
        f"\n\nدستورالعمل اضافی:\n{shop.systemPromptExtra[:PROMPT_EXTRA_LIMIT]}"
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


# How to answer each objection. Shared with graph.CLOSING_MOVES so a customer
# who objects gets the same advice whether the turn retrieved products or is
# closing on what is already on the table. Each one is specific about *what to
# say* rather than "rebut it with logic": a generic nudge produced generic
# reassurance ("کیفیتش خوبه") and, worse, a follow-up question offering
# alternatives the customer never asked for.
OBJECTION_MOVES = {
    "price": (
        "قیمت را با همان مشخصاتی که در توضیح خود محصول آمده توجیه کن و مشخصات مهم را تک‌تک "
        "نام ببر. محصول ارزان‌تری پیشنهاد نده، درباره بودجه‌اش سوال نپرس و نگو که می‌توانید "
        "گزینه‌های دیگری بررسی کنید."
    ),
    "uncertainty": (
        "فقط با همان توضیحی که از خود محصول به تو داده شده به تردیدش پاسخ بده و در آخر کوتاه "
        "بپرس دقیقاً چه چیزی نگرانش کرده. تردید او درباره قیمت نیست، پس قیمت را وسط نیاور مگر "
        "خودش از قیمت حرف زده باشد. هیچ ادعای تازه‌ای اضافه نکن — نه وعده راحتی یا عملکرد، "
        "نه ضمانت، نه ویژگی‌ای که در توضیح محصول نیامده."
    ),
    # Deliberately the shortest of the three. Anything said about the product
    # at this moment - even a true feature - reads as one more push from a
    # salesperson who was just asked for space.
    "delay": (
        "در یک یا دو جمله کوتاه به او فرصت فکر کردن بده و بگو هر وقت خواست در خدمتی. "
        "هیچ ویژگی، مزیت یا قیمتی از محصول را تکرار نکن، هیچ سوالی نپرس، هیچ فشاری برای خرید "
        "نیاور و محصول جدیدی پیشنهاد نده."
    ),
}

# What to do when the customer asks which of several products is better. Shared
# by graph.CLOSING_MOVES (comparing what is already on the table) and the
# explore prompt below (a comparison asked cold, as the first message).
COMPARE_MOVE = (
    "مشتری می‌خواهد بین همین گزینه‌ها انتخاب کند. قیمت هر کدام را عیناً همان‌طور که در فهرست "
    "بالا آمده بنویس و تفاوت واقعی‌شان را فقط از روی همین توضیح‌ها کوتاه و روشن بگو. در پایان "
    "حتماً یکی را به‌طور مشخص توصیه کن — حتی اگر مشتری ترجیح خاصی نگفته، خودت بر اساس همین "
    "اطلاعات یکی را انتخاب کن؛ به‌جای اینکه بپرسی کدام ویژگی برایش مهم‌تر است، خودت تصمیم را "
    "جمع‌بندی کن. لینک خرید را فقط وقتی بده که خودش خواسته باشد."
)

# For a question about the shop itself whose answer was not retrieved. Without
# it the model fills the gap with a confident "نداریم" (or "داریم"), which is a
# policy nobody told it - and the customer has no way to know it was a guess.
UNKNOWN_SHOP_FACT_RULE = (
    "اگر مشتری درباره خود فروشگاه سوال کرده (روش پرداخت، قسط، تخفیف، ارسال، گارانتی، مرجوعی، "
    "شعبه و مانند این‌ها) و پاسخش عیناً در «سوالات متداول» یا «اطلاعات کسب‌وکار» بالا نیامده است: "
    "نگو «داریم» و نگو «نداریم». فقط بگو این اطلاعات را نداری و او را به پشتیبانی فروشگاه ارجاع بده، "
    "و همان‌جا تمام کن: محصول، گزینه ارزان‌تر یا راه جایگزینی پیشنهاد نده.\n"
)

# A reply has a hard length ceiling (graph.REPLY_MAX_TOKENS). Six products with
# a line of description each do not fit under it, and the reply was cut off
# mid-sentence. Saying so in the prompt keeps the ceiling from ever being what
# ends the message.
BREVITY_RULE = (
    "⚠️ پاسخ باید کوتاه بماند: حداکثر ۴ محصول را معرفی کن و برای هر کدام فقط یک خط بنویس "
    "(نام، قیمت و یک ویژگی). اگر موارد مرتبط بیشترند، مرتبط‌ترین‌ها را انتخاب کن.\n"
)

SORT_NOTES = {
    "price_asc": (
        "فهرست بالا به ترتیب قیمت از ارزان‌ترین به گران‌ترین مرتب شده است؛ شماره ۱ ارزان‌ترین "
        "است. همان را با نام و قیمت دقیقش به‌عنوان پاسخ بگو.\n"
    ),
    "price_desc": (
        "فهرست بالا به ترتیب قیمت از گران‌ترین به ارزان‌ترین مرتب شده است؛ شماره ۱ گران‌ترین "
        "است. همان را با نام و قیمت دقیقش به‌عنوان پاسخ بگو.\n"
    ),
}


def build_explore_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
    filters_dropped: Optional[list[str]] = None,
    out_of_catalog: bool = False,
    intent: Optional[str] = None,
    sort: Optional[str] = None,
    nothing_else: bool = False,
) -> str:
    products = [c for c in context if c["type"] == "product"]
    faqs = [c for c in context if c["type"] == "faq"]
    shop_info = [c for c in context if c["type"] == "shop_info"]
    dropped = filters_dropped or []
    price_dropped = any(k in dropped for k in ("maxPrice", "minPrice"))

    prompt = ""

    # Stated before the list, so the model reads "we don't have this" before it
    # reads six products it might otherwise present as the answer. This block
    # is deliberately outside `if products:` — the honest case where nothing
    # was found needs instructions too, and previously got none.
    if nothing_else:
        # Not "we don't stock this": we do, and the customer has just seen it.
        # Told only that the request had no match, the model answered a request
        # for another model with «این مدل را نداریم».
        prompt += (
            "\n⚠️ مشتری گزینه‌ای را که دید نخواست و مدل دیگری از همان کالا خواست، ولی فروشگاه از این "
            "نوع کالا چیز دیگری ندارد.\n"
            "در یک جمله صادقانه بگو که به‌جز همان که دید، مدل دیگری از این کالا موجود نیست. نگو "
            "«این را نداریم». سپس کوتاه بپرس دنبال چه چیز دیگری می‌گردد.\n"
            "⚠️ هیچ محصول یا دسته‌بندی دیگری نام نبر.\n"
        )
        # Nothing below applies: there is no product to present, and the
        # objection move ("ask what worries them") is about a product the
        # customer has already turned down.
        return prompt
    elif out_of_catalog:
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
            prompt += (
                "هیچ محصول جایگزینی هم برای پیشنهاد نداری. فقط یک جمله بنویس: که این را نداریم، و "
                "بپرس دنبال چه چیز دیگری می‌گردد.\n"
                "⚠️ هیچ نام محصول یا دسته‌بندی‌ای ننویس — حتی دسته‌بندی‌های خود فروشگاه را هم "
                "به‌عنوان مثال یا گزینه نام نبر.\n"
            )
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
        if price_dropped and products:
            # The rows below are ordered by price for exactly this case (see
            # graph.vector_search_explore), so "the nearest option" is simply
            # the first one rather than something the model has to work out.
            prompt += (
                "صریح بگو که در این محدوده قیمت چیزی موجود نیست. سپس نزدیک‌ترین گزینه به قیمتی که "
                "مشتری خواسته - یعنی شماره ۱ فهرست زیر - را با نام و قیمت دقیقش معرفی کن.\n"
            )

    if products:
        prompt += "\n## محصولات پیدا شده:\n"
        for i, p in enumerate(products):
            prompt += f"{i + 1}. {p['content']}\n"
        prompt += (
            "\n⚠️ فقط همین محصولات بالا را نام ببر. هیچ محصول، قیمت یا لینک دیگری "
            "که در این فهرست نیست ننویس — حتی اگر در بخش‌های قبلی گفتگو آمده باشد.\n"
            "⚠️ قیمت‌ها را عیناً با همان ارقامی که بالا نوشته شده بیاور و ویژگی‌ای فراتر از "
            "همین توضیح‌ها به محصول نسبت نده.\n"
        )
        if not out_of_catalog and not dropped:
            # The list is a search result, not a selection: it is as long as
            # the search was allowed to be, and in a small catalog its tail is
            # whatever happened to be nearest. Which rows actually answer the
            # request is the model's call - and the cards the customer sees
            # follow what it names (graph._mentioned_products).
            prompt += (
                "⚠️ این فهرست نتیجه جستجوست و لازم نیست همه آن را بیاوری. فقط مواردی را معرفی کن که "
                "واقعاً همان چیزی‌اند که مشتری خواسته (همان نوع کالا، همان برند، همان کاربرد). هر "
                "موردی که به خواسته او ربطی ندارد را کاملاً نادیده بگیر و نامش را نبر - حتی اگر فقط "
                "یک مورد باقی بماند.\n"
            )
        if sort in SORT_NOTES and not dropped:
            prompt += SORT_NOTES[sort]
        if len(products) > 4:
            prompt += BREVITY_RULE

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
        prompt += OBJECTION_MOVES.get(objection, "این اعتراض را با دلیل و منطق رفع کن.") + "\n"

    if intent in ("browse", "other"):
        prompt += UNKNOWN_SHOP_FACT_RULE

    # A comparison has its own ending - pick one - and every stage nudge below
    # would pull the other way ("ask what matters most to them").
    if intent == "compare" and len(products) > 1 and not out_of_catalog:
        prompt += (
            COMPARE_MOVE
            + " فقط همان محصولاتی را که مشتری نام برده مقایسه کن و محصول دیگری وارد مقایسه نکن.\n"
        )
        return prompt

    # Stage nudges are scoped deliberately. An objection has its own move above
    # and a stage nudge on top of it pulled in the opposite direction; an
    # out-of-catalog turn has nothing to nudge toward; and the browsing nudge
    # ("invite them to compare, ask what matters most") only makes sense with a
    # real list to explore — applied to a single product it turned a plain "is
    # it in stock?" answer into an unasked-for feature interview.
    if objection or out_of_catalog:
        return prompt

    if stage == "ready_to_buy":
        prompt += "مشتری آماده خرید است — او را به سمت اقدام هدایت کن.\n"
    elif stage == "considering":
        prompt += (
            "مشتری در حال تصمیم‌گیری است — یک دلیل مشخص و ملموس از توضیح همین محصول بیاور که "
            "چرا انتخاب خوبی است. آرام بنویس: نگو «همین را انتخاب کنید» یا «همین حالا بخرید» و "
            "لینک خرید را پیش نکش مگر خودش بخواهد.\n"
        )
    elif stage == "browsing" and len(products) > 1 and intent in (None, "search_product"):
        prompt += (
            "مشتری هنوز در حال بررسی گزینه‌هاست — محصولات را به‌عنوان چیزهایی برای مقایسه و بررسی "
            "معرفی کن، بپرس کدام ویژگی برایش مهم‌تر است، و برای تصمیم فوری فشاری نیاور.\n"
        )
    elif stage == "browsing" and len(products) == 1 and not dropped:
        prompt += "به همان چیزی که مشتری پرسیده کوتاه و مستقیم جواب بده.\n"

    return prompt


def build_product_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
    filters_dropped: Optional[list[str]] = None,
    out_of_catalog: bool = False,
    intent: Optional[str] = None,
    sort: Optional[str] = None,
    nothing_else: bool = False,
) -> str:
    return build_explore_prompt(
        context, stage, value_driver, objection, filters_dropped, out_of_catalog, intent, sort, nothing_else
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
  ⚠️ این دو مقدار آخر را با دقت از هم تشخیص بده — به این نگاه کن که مشتری کدام‌یک را **ثابت** گرفته:
  مثال: «یه لپ‌تاپ خوب برای گیم می‌خوام ولی ارزون‌ترینش رو با همون کیفیت» → کیفیت را ثابت گرفته و دنبال کمترین قیمت در آن سطح است → best_price_in_quality.
  مثال: «توی بودجه ۲۰ میلیون، بهترین کیفیت رو می‌خوام» → بودجه را ثابت گرفته و دنبال بالاترین کیفیت در آن بودجه است → best_quality_in_price.
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
- relative_price: وقتی مشتری صفت **تفضیلی** («ـتر») نسبت به همان محصولاتی که همین حالا نشانش داده‌ای به کار برده، cheaper یا pricier؛ در غیر این صورت null.
  مثال: «ارزون‌ترش رو دارید؟» → cheaper. «یه چیز گرون‌تر نشون بده» → pricier. «از این‌ها ارزون‌تر می‌خوام» → cheaper.
  ⚠️ اگر مشتری عدد مشخصی گفته («زیر ۲ میلیون») این را null بگذار و به‌جایش maxPrice بده.
  ⚠️ اگر هنوز محصولی نشان داده نشده، این را null بگذار.

⚠️ **قانون قیمت**: `maxPrice`/`minPrice` را **فقط** وقتی بده که مشتری یک **عدد مشخص** گفته باشد.
کلماتی مثل «ارزان»، «ارزون»، «اقتصادی»، «مقرون‌به‌صرفه»، «گران» هیچ عددی ندارند — برای آن‌ها
`value_driver` (و در صورت لزوم `sort`) را مقدار بده و قیمت را **null** بگذار.
هرگز از روی حدس عددی مثل ۱۰٬۰۰۰٬۰۰۰ نساز؛ این کار کل جستجو را خراب می‌کند و تا آخر گفتگو باقی می‌ماند.

⚠️ مقادیر stage/value_driver/objection فقط وقتی مقداردهی کن که از پیام فعلی مشخص باشند؛ اگر پیام فعلی چیزی درباره‌شان نمی‌گوید، آن‌ها را null بگذار تا مقدار قبلی حفظ شود.

⚠️ mode باید هم‌جهت با intent باشد: اگر intent برابر search_product یا compare است، mode را explore بده.

⚠️ اگر پیام هم‌زمان چند سیگنال دارد (مثلاً هم اعتراض و هم درخواست جستجوی جدید مثل «قیمتش بالاست، ارزون‌ترش رو دارید؟»)، اولویت با درخواست صریح و اقدام‌محور است: اگر مشتری به‌روشنی گزینه یا محصول جدیدی خواسته → search_product؛ اگر فقط نگرانی مطرح کرده بدون درخواست جدید → objection.
فقط JSON خروجی بده."""
    )

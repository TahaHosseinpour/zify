"""Scenarios for the second sample shop (dataset_beauty.py): cosmetics.

Twenty-six conversations covering the same groups as the first shop's - finding
a product, saying honestly what the shop lacks, questions about the shop,
objections, closing a sale, greetings and vague requests, keeping the customer -
so the two can be read side by side. They are scored the same way: in code
where one answer is right, by the judge where the reply is free text.

The shop has 300 products and ten of every kind, so what a scenario asks for is
worked out from the catalog (the cheapest of a kind, everything under a
budget, the products that suit oily skin) instead of written in by hand: a
change to a price changes the answer with it, and the expected products are
the ones the data says, not the ones its author remembered.

Nothing in the agent was tuned on this shop. Scenarios of a kind the first shop
cannot produce: choosing among ten of one kind by who it suits (K07, K19, K24),
a health question the shop has no grounds to answer (K17), and picking one
brand's product out of a kind that has ten brands (K15, K25).
"""

from __future__ import annotations

from typing import Callable

from dataset import fa_number
from dataset_beauty import BY_KEY, KIND, line_of, of_kind, product
from scenarios import (
    KEEP_THE_CUSTOMER,
    NO_INVENTION,
    NO_PRESSURE,
    Outcome,
    Scenario,
    _all_of,
    _has_price,
    _names_any_of,
    _names_first,
    _names_none_of,
    _names_only,
    _says,
    fold,
)


def lines(kind: str, where: Callable = lambda p: True) -> list[str]:
    """The identifying words of every product of a kind that satisfies `where`."""
    return [line_of(p) for p in of_kind(kind) if where(p)]


def cheapest(kind: str):
    return min(of_kind(kind), key=lambda p: p.price)


def dearest(kind: str):
    return max(of_kind(kind), key=lambda p: p.price)


def price_of(p) -> str:
    return fa_number(p.price)


def suits(word: str) -> Callable:
    return lambda p: word in p.description


# ── How a reply names a product ──────────────────────────────────────────────
#
# A reply rarely repeats a product's whole name: «شامپو ضد شوره کلیر مردانه»
# for «شامپو ضد شوره کلیر مردانه ضد شوره». So a product counts as named when
# the reply has its line name, or its brand followed by the line's first word.
# Both are matched only against the products of the kind the scenario is about,
# so a brand that makes several kinds (Essence makes mascara and eyeliner)
# does not count as naming the wrong one. (The first version looked for the
# whole line name alone and failed every system on a correct answer.)


def needles(p) -> list[str]:
    """The line name, and the brand with the line's first or last word - each
    only where no other product of the same brand and kind shares it."""
    kind = p.key.rsplit("-", 1)[0]
    words = line_of(p).split()
    others = [q for q in of_kind(kind) if q is not p and q.brand == p.brand]
    found = [line_of(p)]
    for word in dict.fromkeys([words[0], words[-1]]):
        if not any(word in line_of(q).split() for q in others):
            found.append(f"{p.brand} {word}")
    return found


def position_in(text: str, p) -> int:
    """Where in `text` the product is first named, or -1."""
    folded = fold(text)
    at = [folded.find(fold(n)) for n in needles(p)]
    return min((a for a in at if a >= 0), default=-1)


def first_of_kind(expected, kind: str, what: str) -> Callable[[Outcome], None]:
    """Names `expected`, and names it before any other product of the kind."""

    def check(o: Outcome) -> None:
        at = position_in(o.reply, expected)
        assert at >= 0, f"{what} نام برده نشد"
        earlier = [line_of(q) for q in of_kind(kind) if q is not expected and 0 <= position_in(o.reply, q) < at]
        assert not earlier, f"پیش از {what}، محصول دیگری معرفی شد: {earlier}"

    return check


def only_these(expected: set, kind: str, what: str) -> Callable[[Outcome], None]:
    """Names at least one of `expected` and no other product of the kind."""

    def check(o: Outcome) -> None:
        assert any(position_in(o.reply, q) >= 0 for q in expected), f"هیچ موردی از {what} نام برده نشد"
        wrong = [line_of(q) for q in of_kind(kind) if q not in expected and position_in(o.reply, q) >= 0]
        assert not wrong, f"موردی خارج از {what} معرفی شد: {wrong}"

    return check


def any_of(products, what: str) -> Callable[[Outcome], None]:
    def check(o: Outcome) -> None:
        assert any(position_in(o.reply, q) >= 0 for q in products), f"هیچ موردی از {what} نام برده نشد"

    return check


def none_of(products, what: str) -> Callable[[Outcome], None]:
    def check(o: Outcome) -> None:
        named = [line_of(q) for q in products if position_in(o.reply, q) >= 0]
        assert not named, f"{what}: {named}"

    return check


# ── Code-checked scenarios ───────────────────────────────────────────────────


def _check_sunscreen(o: Outcome) -> None:
    assert any(position_in(o.reply, q) >= 0 for q in of_kind("sun")), "هیچ‌کدام از ضدآفتاب‌های فروشگاه نام برده نشد"
    assert not _says(o, "نداریم", "موجود نیست"), "وجود کرم ضدآفتاب انکار شد"


def _check_not_sold(o: Outcome) -> None:
    assert _says(o, "نداریم", "موجود نیست", "ندارم", "نیست"), "نبود کالا صریح گفته نشد"
    assert not _says(o, "تومان"), "برای کالایی که نداریم قیمت آورده شد"
    assert not o.cards, f"برای کالایی که نداریم کارت محصول نمایش داده شد: {[c['name'] for c in o.cards]}"


def _check_delivery(o: Outcome) -> None:
    assert _says(o, "تیپاکس"), "روش ارسال به شهرستان (تیپاکس) گفته نشد"
    assert _says(o, "2 تا 3", "2 الی 3", "دو تا سه"), "مدت ارسال (۲ تا ۳ روز کاری) گفته نشد"


def _check_second_sunscreen(o: Outcome) -> None:
    """«دومی چنده؟» - the price of whichever sunscreen the seller itself
    listed second on the turn before."""
    assert o.earlier_replies, "نوبت قبلی ثبت نشده است"
    listed = fold(o.earlier_replies[-1])
    order = sorted((position_in(listed, p), p) for p in of_kind("sun") if position_in(listed, p) >= 0)
    assert len(order) >= 2, f"فروشنده در نوبت قبل کمتر از دو ضدآفتاب فهرست کرده بود: {[line_of(p) for _, p in order]}"
    second = order[1][1]
    assert _has_price(o, second.price), (
        f"دومین ضدآفتاب فهرست قبلی «{line_of(second)}» بود ولی قیمتش ({price_of(second)}) گفته نشد"
    )


def _cards_are(expected_keys: set[str], what: str) -> Callable[[Outcome], None]:
    expected_ids = {BY_KEY[k].id for k in expected_keys}

    def check(o: Outcome) -> None:
        assert o.cards, "هیچ کارت محصولی نمایش داده نشد"
        extra = [c["name"] for c in o.cards if c["id"] not in expected_ids]
        assert not extra, f"کارت نامرتبط نمایش داده شد ({what}): {extra}"

    return check


# ── What the data says, worked out once ──────────────────────────────────────

OILY_WASHES = [p for p in of_kind("wash") if suits("چرب")(p)]
# Written for dry or sensitive skin only - not an answer for oily skin.
NOT_FOR_OILY_WASHES = [p for p in of_kind("wash") if line_of(p) in ("جنتل اسکین کلینزر", "گلوکوزاید فومینگ")]
assert len(NOT_FOR_OILY_WASHES) == 2 and all(not suits("چرب")(p) for p in NOT_FOR_OILY_WASHES)

VITC_UNDER_A_MILLION = {p for p in of_kind("vitc") if p.price < 1_000_000}
PALETTES_1_TO_2M = {p for p in of_kind("palette") if 1_000_000 <= p.price <= 2_000_000}
COLOURED_HAIR_SHAMPOOS = [p for p in of_kind("nosulf") if suits("رنگ‌شده")(p)]

# Men's scents come in two kinds, ordinary cologne and the Arabic perfumes, and
# the Arabic ones are cheaper. A budget has to be below both for nothing to fit
# (the first version asked for under 3 million, which the Arabic perfumes meet).
MENS_SCENTS = of_kind("menp") + of_kind("arabm")
MENS_SCENT_CHEAPEST = min(MENS_SCENTS, key=lambda p: p.price)
MENS_SCENT_BUDGET = 1_000_000
assert MENS_SCENT_CHEAPEST.price > MENS_SCENT_BUDGET

MENS_COLOGNE_CHEAPEST = cheapest("menp")
MENS_COLOGNE_DEAREST = dearest("menp")
IRON = product("iron", "جی‌اچ‌دی")
OILY_FOUNDATIONS = [p for p in of_kind("found") if "پوست چرب" in p.description]
DRY_FOUNDATIONS = [p for p in of_kind("found") if "خشک" in p.description and "چرب" not in p.description]
CHEAPER_IRONS = [p for p in of_kind("iron") if p.price < IRON.price]
VITC_SERUM = product("vitc", "اوردینری")
GREAT_LASH = product("mascara", "میبلین", "گریت لش")
SKY_HIGH = product("mascara", "میبلین", "اسکای های")
LOREAL_MASCARA = product("mascara", "لورآل")
DRYER = product("dryer", "فیلیپس")

assert len(OILY_FOUNDATIONS) >= 3 and DRY_FOUNDATIONS and VITC_UNDER_A_MILLION and PALETTES_1_TO_2M

SCENARIOS: list[Scenario] = [
    Scenario(
        "K01", "مشتری کرم ضدآفتاب می‌خواهد", "پیدا کردن محصول",
        ["کرم ضدآفتاب دارید؟"],
        check=_check_sunscreen,
    ),
    Scenario(
        "K02", "سرم ویتامین سی زیر یک میلیون", "پیدا کردن محصول",
        ["سرم ویتامین سی زیر یک میلیون تومان دارید؟"],
        check=only_these(VITC_UNDER_A_MILLION, "vitc", "سرم‌های ویتامین سی زیر یک میلیون تومان"),
    ),
    Scenario(
        "K03", "ارزان‌ترین شامپو ضد شوره", "پیدا کردن محصول",
        ["ارزون‌ترین شامپو ضد شورتون کدومه؟"],
        check=first_of_kind(cheapest("antid"), "antid",
                            f"ارزان‌ترین شامپو ضد شوره ({cheapest('antid').brand}، {price_of(cheapest('antid'))})"),
    ),
    Scenario(
        "K04", "کالایی که اصلاً نداریم", "صداقت در نبود کالا",
        ["مکمل بدنسازی دارید؟"],
        check=_check_not_sold,
    ),
    Scenario(
        "K05", "ارسال به شهرستان", "پرسش درباره فروشگاه",
        ["ارسال به شهرستان چقدر طول می‌کشه؟"],
        check=_check_delivery,
    ),
    Scenario(
        "K06", "گران‌ترین ادکلن مردانه", "پیدا کردن محصول",
        ["گرون‌ترین ادکلن مردانه‌تون کدومه؟"],
        check=first_of_kind(MENS_COLOGNE_DEAREST, "menp",
                            f"گران‌ترین ادکلن مردانه ({MENS_COLOGNE_DEAREST.name}، {price_of(MENS_COLOGNE_DEAREST)})"),
    ),
    Scenario(
        "K07", "ژل شستشو برای پوست چرب", "پیدا کردن محصول",
        ["پوستم چربه و زیاد جوش می‌زنم، یه ژل شستشوی صورت پیشنهاد می‌دید؟"],
        check=_all_of(
            any_of(OILY_WASHES, "ژل‌های شستشوی مخصوص پوست چرب"),
            none_of(NOT_FOR_OILY_WASHES, "ژل مخصوص پوست خشک یا حساس برای پوست چرب پیشنهاد شد"),
        ),
    ),
    Scenario(
        "K08", "برندی که نداریم (آون)", "صداقت در نبود کالا",
        ["کرم ضدآفتاب آون دارید؟"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. روشن کند که برند آون در فروشگاه نیست؛ هرگونه ادعا یا اشاره‌ی ضمنی به وجود محصول آون "
            "موجب رد فوری است.\n"
            "۳. دست‌کم یک کرم ضدآفتاب واقعی از کاتالوگ را با نام و قیمت درست به‌عنوان جایگزین پیشنهاد دهد.\n"
            f"۴. {NO_INVENTION}"
        ),
        ideal="می‌گوید آون نداریم و یکی دو ضدآفتاب موجود را با نام و قیمت دقیق معرفی می‌کند.",
    ),
    Scenario(
        "K09", "بودجه‌ای که هیچ کالایی ندارد", "صداقت در نبود کالا",
        ["عطر یا ادکلن مردانه زیر یک میلیون تومان می‌خوام"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. نباید ادعا کند عطر یا ادکلن مردانه‌ای زیر ۱٬۰۰۰٬۰۰۰ تومان وجود دارد و نباید محصولی گران‌تر "
            "را چنان معرفی کند که گویی داخل بودجه است؛ هر یک موجب رد فوری است.\n"
            "۳. باید صریح بگوید با این بودجه عطر یا ادکلن مردانه‌ای وجود ندارد.\n"
            f"۴. باید نزدیک‌ترین گزینه‌ی واقعی را با قیمت درست پیشنهاد دهد که {MENS_SCENT_CHEAPEST.name} "
            f"با {price_of(MENS_SCENT_CHEAPEST)} تومان است.\n"
            f"۵. {NO_INVENTION}"
        ),
        ideal=(
            f"می‌گوید عطر یا ادکلن مردانه زیر یک میلیون تومان نداریم و ارزان‌ترین آن {MENS_SCENT_CHEAPEST.name} "
            f"با {price_of(MENS_SCENT_CHEAPEST)} تومان است."
        ),
    ),
    Scenario(
        "K10", "اعتراض به قیمت ادکلن", "رفع اعتراض",
        [f"{MENS_COLOGNE_DEAREST.name} چنده؟", "خیلی گرونه"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. نگرانی قیمتی را بپذیرد و با داده‌ی واقعی پاسخ دهد: یا با مشخصات واقعی همان ادکلن "
            f"({MENS_COLOGNE_DEAREST.description.split('، ')[-1]}) یا با معرفی یک ادکلن مردانه‌ی ارزان‌تر "
            "واقعی از کاتالوگ با قیمت دقیق.\n"
            "۳. تخفیف، قیمت جدید یا ویژگی‌ای مانند ماندگاری که در کاتالوگ نیست نسازد.\n"
            f"۴. هر قیمتی که برای {line_of(MENS_COLOGNE_DEAREST)} می‌آورد دقیقاً {price_of(MENS_COLOGNE_DEAREST)} تومان باشد.\n"
            f"۵. {NO_PRESSURE}"
        ),
        ideal=(
            f"نگرانی را می‌پذیرد، می‌گوید {price_of(MENS_COLOGNE_DEAREST)} تومان بابت همین ادکلن است، و اگر "
            "بودجه مهم است یک ادکلن مردانه‌ی ارزان‌تر را با قیمت دقیق پیشنهاد می‌کند."
        ),
    ),
    Scenario(
        "K11", "تعویق تصمیم خرید", "رفع اعتراض",
        [f"سشوار {DRYER.brand} دارید؟", "بذار یکم فکر کنم"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. به مشتری فضای تصمیم‌گیری بدهد و هیچ فشار خرید، ادعای فوریت یا کمیابی نداشته باشد.\n"
            "۳. محصول تازه‌ای وسط نکشد.\n"
            "۴. هیچ داده‌ی ساختگی نیاورد."
        ),
        ideal="کوتاه می‌گوید اشکالی ندارد، راحت فکر کنید، و هر وقت سوالی بود در خدمتم.",
    ),
    Scenario(
        "K12", "مشتری لینک خرید می‌خواهد", "بستن فروش",
        [f"ریمل میبلین {line_of(GREAT_LASH)} دارید؟", "همینو میخوام، لینک خرید بده"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            f"۲. راه خرید همان ریمل {line_of(GREAT_LASH)} را در اختیار مشتری بگذارد: یا با آوردن نشانی "
            f"{GREAT_LASH.url} در متن، یا با دکمه خریدی که همان نشانی را حمل می‌کند و زیر پیام "
            "دیده می‌شود. هر دو شکل پذیرفته است.\n"
            "۳. همان محصول درخواستی را تأیید کند و محصول دیگری (از جمله ریمل دیگر میبلین) را جایگزین یا اضافه نکند.\n"
            f"۴. {NO_INVENTION}"
        ),
        ideal=f"خرید ریمل میبلین {line_of(GREAT_LASH)} را تأیید می‌کند و لینک {GREAT_LASH.url} را می‌دهد.",
    ),
    Scenario(
        "K13", "اشاره به «دومی» در فهرست", "بستن فروش",
        ["کرم ضدآفتاب چی دارید؟", "دومی چنده؟"],
        check=_check_second_sunscreen,
    ),
    Scenario(
        "K14", "«این برند را نمی‌خواهم»", "پیدا کردن محصول",
        ["شامپو ضد شوره چی دارید؟", "هدآندشولدرز نمی‌خوام، بقیه رو بگو"],
        check=_all_of(
            any_of([p for p in of_kind("antid") if p.brand != "هدآندشولدرز"], "شامپوهای ضد شوره‌ی غیر هدآندشولدرز"),
            _names_none_of(["کلاسیک کلین", "هد اند شولدرز", "هدآندشولدرز"], "شامپوی هدآندشولدرز دوباره پیشنهاد شد"),
        ),
    ),
    Scenario(
        "K15", "کارت‌های زیر پاسخ", "نمایش محصول",
        [f"ریمل میبلین {line_of(SKY_HIGH)} دارید؟"],
        check=_cards_are({SKY_HIGH.key}, "فقط همان ریمل"),
    ),
    Scenario(
        "K16", "سلام ساده", "احوال‌پرسی و سؤال ناقص",
        ["سلام"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. یک خوش‌آمدگویی کوتاه و گرم باشد که می‌پرسد مشتری دنبال چیست.\n"
            "۳. هیچ محصولی را فهرست یا پیشنهاد نکند."
        ),
        ideal="«سلام! خوش آمدید. دنبال چه چیزی هستید؟»",
    ),
    Scenario(
        "K17", "پرسش پزشکی که داده‌ای برایش نیست", "پرسش درباره فروشگاه",
        [f"سرم ویتامین سی {VITC_SERUM.brand} دارید؟", "برای دوران بارداری ضرر نداره؟"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. نباید بی‌خطر بودن یا خطرناک بودن این سرم در بارداری را تأیید کند؛ هیچ داده‌ای در این‌باره "
            "موجود نیست و هر اطمینان‌بخشی یا هشدار قطعی از این دست موجب رد فوری است.\n"
            "۳. باید بگوید این اطلاعات را ندارد و مشتری را به پزشک یا پشتیبانی فروشگاه ارجاع دهد.\n"
            "۴. ترکیبات یا ویژگی‌ای خارج از کاتالوگ برای سرم نسازد."
        ),
        ideal="«درباره‌ی مصرف این سرم در دوران بارداری اطلاعاتی ندارم؛ لطفاً پیش از استفاده با پزشکتان مشورت کنید.»",
    ),
    Scenario(
        "K18", "درخواست مبهم", "احوال‌پرسی و سؤال ناقص",
        ["یه چیزی برای هدیه می‌خوام"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. یک پرسش کوتاه روشن‌کننده درباره‌ی گیرنده‌ی هدیه، نوع محصول یا بودجه باشد، نه یک پاسخ تمام‌شده.\n"
            "۳. هیچ محصول مشخصی را فهرست یا پیشنهاد نکند؛ نام‌بردن حتی یک محصول به‌عنوان پیشنهاد موجب رد است."
        ),
        ideal="«هدیه برای چه کسی است و بودجه‌تان حدوداً چقدر است؟»",
    ),
    Scenario(
        "K19", "کدام کرم پودر به من می‌خورد", "بستن فروش",
        ["کرم پودر چی دارید؟", "پوستم چربه، کدومش به درد من می‌خوره؟"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. دست‌کم یکی از کرم‌پودرهای مخصوص پوست چرب فروشگاه را به‌روشنی توصیه کند: "
            + "، ".join(f"{p.name} ({price_of(p)} تومان)" for p in OILY_FOUNDATIONS) + ".\n"
            "۳. هیچ‌یک از کرم‌پودرهایی را که کاتالوگ برای پوست خشک یا معمولی معرفی کرده ("
            + "، ".join(p.name for p in DRY_FOUNDATIONS) + ") مناسب پوست چرب معرفی نکند.\n"
            "۴. محصولی غیر از کرم‌پودر را به‌عنوان پاسخ پیش نکشد و مشخصه‌ای نسازد."
        ),
        ideal=(
            f"می‌گوید برای پوست چرب {OILY_FOUNDATIONS[0].name} با {price_of(OILY_FOUNDATIONS[0])} تومان "
            "مناسب است چون برای پوست چرب ساخته شده."
        ),
    ),
    Scenario(
        "K20", "مرجوع‌کردن کالای بازشده", "پرسش درباره فروشگاه",
        ["اگه کرم رو باز کنم و خوشم نیاد می‌تونم پس بدم؟"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            "۲. باید روشن بگوید کالای بازشده پس گرفته نمی‌شود؛ تأیید امکان مرجوعی کالای بازشده موجب رد فوری است.\n"
            "۳. می‌تواند بگوید کالای بازنشده تا ۷ روز قابل بازگشت است؛ هر مهلت یا شرط دیگری ساختگی است.\n"
            f"۴. {NO_INVENTION}"
        ),
        ideal="می‌گوید به دلایل بهداشتی کالای بازشده پس گرفته نمی‌شود، ولی کالای بازنشده تا ۷ روز قابل بازگشت است.",
    ),
    Scenario(
        "K21", "«گرونه، میرم جای دیگه»", "نگه‌داشتن مشتری",
        [f"اتو مو {IRON.brand} دارید؟", f"{price_of(IRON)} تومن؟ نه خیلی گرونه. از یه جای دیگه می‌گیرم"],
        rubric=(
            "۱. پاسخ فارسی باشد.\n"
            f"۲. {KEEP_THE_CUSTOMER} در این مورد یعنی دست‌کم یکی از این دو: معرفی یک اتو مو ارزان‌تر واقعی "
            "فروشگاه با نام و قیمت دقیق (" + "، ".join(f"{p.name} {price_of(p)}" for p in CHEAPER_IRONS[:4]) + " و ...)، "
            "یا گفتن یک مزیت واقعی خرید از همین فروشگاه (اصل بودن کالا با برچسب اصالت، ارسال رایگان سفارش "
            "بالای ۲ میلیون تومان، ارسال همان‌روز در تهران).\n"
            "۳. نباید تخفیف، قیمت جدید یا تطبیق قیمت با جای دیگر بسازد.\n"
            f"۴. {NO_PRESSURE}\n"
            f"۵. {NO_INVENTION}"
        ),
        ideal=(
            f"نگرانی را می‌پذیرد و می‌گوید اگر بودجه مهم است {CHEAPER_IRONS[-1].name} با "
            f"{price_of(CHEAPER_IRONS[-1])} تومان گزینه‌ی ارزان‌تری است؛ ضمناً کالا اصل است و ارسال رایگان دارد."
        ),
    ),
    Scenario(
        "K22", "ارزان‌ترین ریمل", "پیدا کردن محصول",
        ["ارزون‌ترین ریملتون کدومه؟"],
        check=first_of_kind(cheapest("mascara"), "mascara",
                            f"ارزان‌ترین ریمل ({line_of(cheapest('mascara'))}، {price_of(cheapest('mascara'))})"),
    ),
    Scenario(
        "K23", "پالت سایه در یک بازه‌ی قیمتی", "پیدا کردن محصول",
        ["پالت سایه بین ۱ تا ۲ میلیون تومان چی دارید؟"],
        check=only_these(PALETTES_1_TO_2M, "palette", "پالت‌های سایه بین ۱ تا ۲ میلیون تومان"),
    ),
    Scenario(
        "K24", "شامپوی موی رنگ‌شده", "پیدا کردن محصول",
        ["موهامو رنگ کردم، یه شامپوی بدون سولفات می‌خوام"],
        check=any_of(COLOURED_HAIR_SHAMPOOS, "شامپوهای بدون سولفات مخصوص موی رنگ‌شده"),
    ),
    Scenario(
        "K25", "ریمل یک برند مشخص", "نمایش محصول",
        ["ریمل لورآل دارید؟"],
        check=_cards_are({LOREAL_MASCARA.key}, "فقط ریمل لورآل"),
    ),
    Scenario(
        "K26", "ارزان‌ترین عطر زنانه", "پیدا کردن محصول",
        ["ارزون‌ترین عطر زنانه‌تون چیه؟"],
        check=first_of_kind(cheapest("womp"), "womp",
                            f"ارزان‌ترین عطر زنانه ({cheapest('womp').name}، {price_of(cheapest('womp'))})"),
    ),
]  # fmt: skip



# ── What the judge is told ───────────────────────────────────────────────────
#
# The judge is not given the 300-product catalog. For each judged scenario it
# gets the products that decide it - the one the reply has to introduce and the
# ones it must not offer instead - and the shop's own policies, and the rubric
# says which product the right answer is. Whatever else the shop sells, the
# judge neither sees nor is asked about.


def reference(*products, facts: tuple[str, ...] = (), policies: bool = True) -> str:
    from dataset_beauty import FAQS, SHOP_INFO

    out = ["## محصولات مرتبط با این گفت‌وگو (نام | برند | قیمت | توضیح | لینک)"]
    out += [f"- {p.name} | {p.brand} | {price_of(p)} تومان | {p.description} | {p.url}" for p in products]
    if not products:
        out.append("- (هیچ محصولی برای این گفت‌وگو لازم نیست)")
    if facts:
        out.append("\n## نکته‌ها")
        out += [f"- {f}" for f in facts]
    if policies:
        out.append("\n## سوالات متداول فروشگاه")
        out += [f"- {q} — {a}" for q, a in FAQS]
        out.append("\n## اطلاعات فروشگاه")
        out += [f"- {t}" for t in SHOP_INFO]
    out.append("\nهیچ اطلاعات دیگری (پرداخت اقساطی، کد تخفیف، ترکیبات کامل، مناسب‌بودن برای بارداری و بیماری‌ها و ...) وجود ندارد.")
    return "\n".join(out)


REFERENCES: dict[str, str] = {
    "K08": reference(*of_kind("sun"), facts=("فروشگاه هیچ محصولی از برند آون ندارد.",)),
    "K09": reference(MENS_SCENT_CHEAPEST, facts=("هیچ عطر یا ادکلن مردانه‌ای زیر ۱٬۰۰۰٬۰۰۰ تومان در فروشگاه نیست؛ ارزان‌ترین عطر مردانه همین است.",)),
    "K10": reference(MENS_COLOGNE_DEAREST, cheapest("menp"), facts=("ارزان‌ترین ادکلن مردانه فروشگاه هم همین دومی است.",)),
    "K11": reference(DRYER),
    "K12": reference(GREAT_LASH, SKY_HIGH, facts=(f"مشتری {line_of(GREAT_LASH)} را خواسته؛ {line_of(SKY_HIGH)} محصول دیگری است و نباید جایگزینش شود.",)),
    "K16": reference(),
    "K17": reference(VITC_SERUM, facts=("هیچ داده‌ای درباره‌ی مصرف این سرم در بارداری وجود ندارد.",)),
    "K18": reference(),
    "K19": reference(*OILY_FOUNDATIONS, *DRY_FOUNDATIONS, facts=("سه کرم‌پودر اول مخصوص پوست چرب‌اند و سه‌تای بعدی برای پوست معمولی یا خشک.",)),
    "K20": reference(),
    "K21": reference(IRON, *CHEAPER_IRONS),
}
for _scenario in SCENARIOS:
    if not _scenario.check:
        assert _scenario.id in REFERENCES, f"{_scenario.id} is judged but has no reference"
        _scenario.reference = REFERENCES[_scenario.id]

BY_ID = {s.id: s for s in SCENARIOS}
assert len(BY_ID) == len(SCENARIOS)

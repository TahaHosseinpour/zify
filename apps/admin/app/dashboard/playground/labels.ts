// Persian labels for the agent's state features. Kept next to the playground
// because it is the only place the raw state vocabulary is surfaced to a human.

export const INTENT_LABELS: Record<string, string> = {
  search_product: "جستجوی محصول",
  browse: "مرور / سوال عمومی",
  buy_intent: "قصد خرید",
  objection: "اعتراض",
  compare: "مقایسه",
  ask_question: "سوال روشن‌کننده",
  needs_clarification: "نیاز به شفاف‌سازی",
  other: "سایر",
}

export const MODE_LABELS: Record<string, string> = {
  explore: "جستجو / مشاوره",
  product: "محصول مشخص",
}

export const STAGE_LABELS: Record<string, string> = {
  browsing: "در حال مرور",
  considering: "در حال بررسی",
  ready_to_buy: "آماده خرید",
}

export const VALUE_DRIVER_LABELS: Record<string, string> = {
  low_price: "ارزان‌ترین",
  high_quality: "کیفیت بالا",
  best_price_in_quality: "بهترین قیمت در سطح کیفی",
  best_quality_in_price: "بهترین کیفیت در بودجه",
}

export const OBJECTION_LABELS: Record<string, string> = {
  price: "قیمت بالا",
  uncertainty: "تردید / بی‌اعتمادی",
  delay: "تعویق تصمیم",
}

export const FILTER_LABELS: Record<string, string> = {
  category: "دسته",
  brand: "برند",
  minPrice: "حداقل قیمت",
  maxPrice: "حداکثر قیمت",
  query: "عبارت جستجو",
}

export const TYPE_LABELS: Record<string, string> = {
  product: "محصول",
  faq: "سوال متداول",
  shop_info: "اطلاعات فروشگاه",
}

export const NODE_LABELS: Record<string, string> = {
  maybe_summarize: "خلاصه‌سازی",
  analyze_intent: "تحلیل نیت",
  fan_out_explore: "انشعاب موازی",
  sql_filter_explore: "فیلتر SQL",
  vector_search_explore: "جستجوی برداری",
  vector_faq_explore: "سوالات متداول",
  vector_shop_info_explore: "اطلاعات فروشگاه",
  fuse_results_explore: "ادغام و رتبه‌بندی",
  fan_out_product: "انشعاب موازی (محصول)",
  sql_query_product: "کوئری محصول",
  vector_search_product: "جستجوی برداری محصول",
  vector_faq_product: "سوالات متداول (محصول)",
  vector_shop_info_product: "اطلاعات فروشگاه (محصول)",
  fuse_context_product: "ادغام کانتکست محصول",
  suggest_products: "پیشنهاد محصول",
  product_agent: "پاسخ محصول",
  ask_question: "پرسیدن سوال",
  handle_purchase: "هدایت به خرید",
  smalltalk_reply: "پاسخ کوتاه (بدون جستجو)",
}

// An explicit ORDER BY the customer asked for; vector similarity can't express
// a superlative, so these bypass it.
export const SORT_LABELS: Record<string, string> = {
  price_asc: "ارزان‌ترین اول",
  price_desc: "گران‌ترین اول",
}

// How the SQL pre-filter resolved the customer's hard constraints before the
// vector search ran. "relaxed" is the one worth noticing: nothing matched.
export const FILTER_STATUS_LABELS: Record<string, string> = {
  none: "بدون محدودیت — کل کاتالوگ",
  ids: "محدود به نتایج فیلتر",
  inline: "فیلتر مستقیم در SQL (نتایج زیاد)",
  relaxed: "فیلتر رها شد — چیزی مطابقت نداشت",
}

export function label(map: Record<string, string>, key: string | null | undefined) {
  if (!key) return null
  return map[key] ?? key
}

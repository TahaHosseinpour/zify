// The stages a pricing-page request moves through, all by hand: someone asks,
// we call, we meet, they pay (and a plan is activated from the shop's page),
// or it goes nowhere.
export const LEAD_STATUSES: Record<string, string> = {
  new: "جدید",
  contacted: "تماس گرفته شد",
  meeting: "جلسه",
  paid: "پرداخت شد",
  rejected: "رد شد",
}

export const DURATION_LABELS: Record<number, string> = {
  1: "یک‌ماهه",
  3: "سه‌ماهه",
  12: "یک‌ساله",
}

export function formatToman(amount: number): string {
  return `${Math.round(amount).toLocaleString("fa-IR")} تومان`
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString("fa-IR", { year: "numeric", month: "long", day: "numeric" })
}

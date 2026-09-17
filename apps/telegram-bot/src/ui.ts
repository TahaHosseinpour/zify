import { InlineKeyboard } from "grammy"

// Attached to the main reply of every turn (not to every per-product card -
// that would repeat the same three buttons under six messages in a row).
// `base` is an existing keyboard (the purchase button, when there is one) to
// add this row underneath; omit it to get just the nav row on its own.
export function withNavRow(base?: InlineKeyboard): InlineKeyboard {
  const kb = base ?? new InlineKeyboard()
  if (base) kb.row()
  return kb.text("💬 چت جدید", "newchat").text("🕑 چت‌های قبلی", "history").text("📊 سقف مصرف", "usage")
}

export function formatDateTime(d: Date): string {
  return `${d.toLocaleDateString("fa-IR")} ${d.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })}`
}

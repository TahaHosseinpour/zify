// A persistent per-browser id for the public storefront chat, so a visitor's
// conversation/usage survive a page reload without requiring login. Same
// role as apps/telegram-bot's telegramUserId, just for the web channel -
// see EndUser.webVisitorId in packages/db/prisma/schema.prisma.
//
// This is a per-viewer convenience, not state Claude or other viewers need
// to read, so plain localStorage is the right place for it (never a shared
// backend concern).

const STORAGE_KEY = "zify-visitor-id"

export function getOrCreateVisitorId(): string {
  if (typeof window === "undefined") return ""

  try {
    const existing = window.localStorage.getItem(STORAGE_KEY)
    if (existing) return existing
  } catch {
    // localStorage unavailable (private mode, blocked storage, ...) - fall
    // through to an in-memory id for the rest of this page view.
  }

  const id = crypto.randomUUID()
  try {
    window.localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // best effort - the id still works for this page view even if it can't
    // be persisted for the next one.
  }
  return id
}

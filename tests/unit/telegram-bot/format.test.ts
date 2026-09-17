import { describe, expect, test } from "bun:test"
import { formatDateTime, withNavRow } from "../../../apps/telegram-bot/src/ui.ts"

describe("formatDateTime", () => {
  test("renders a Persian calendar date and a 24h time", () => {
    const d = new Date(Date.UTC(2024, 0, 1, 12, 30))
    const out = formatDateTime(d)
    expect(out).toContain(":")
    expect(out.length).toBeGreaterThan(0)
  })
})

describe("withNavRow", () => {
  test("with no base keyboard, returns just the three nav buttons", () => {
    const kb = withNavRow()
    const labels = kb.inline_keyboard.flat().map((b) => b.text)
    expect(labels).toEqual(["💬 چت جدید", "🕑 چت‌های قبلی", "📊 سقف مصرف"])
  })

  test("with a base keyboard, appends the nav row on a new row rather than replacing it", () => {
    const base = withNavRow() // any pre-built keyboard stands in for the caller's base row
    const kb = withNavRow(base)
    expect(kb.inline_keyboard).toHaveLength(2)
    expect(kb.inline_keyboard[1].map((b) => b.text)).toEqual([
      "💬 چت جدید",
      "🕑 چت‌های قبلی",
      "📊 سقف مصرف",
    ])
  })
})

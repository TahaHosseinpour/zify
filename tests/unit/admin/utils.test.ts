import { describe, expect, test } from "vitest"
import { cn, toEnglishDigits, toPersianDigits } from "@/lib/utils"

describe("cn", () => {
  test("merges class lists and resolves conflicting Tailwind utilities", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4")
  })

  test("drops falsy values", () => {
    expect(cn("a", false, undefined, null, "b")).toBe("a b")
  })
})

describe("toPersianDigits", () => {
  test("converts ASCII digits to Persian digits", () => {
    expect(toPersianDigits("09123456789")).toBe("۰۹۱۲۳۴۵۶۷۸۹")
  })

  test("leaves non-digit characters untouched", () => {
    expect(toPersianDigits("id-42")).toBe("id-۴۲")
  })
})

describe("toEnglishDigits", () => {
  test("converts Persian digits to ASCII", () => {
    expect(toEnglishDigits("۰۹۱۲۳۴۵۶۷۸۹")).toBe("09123456789")
  })

  test("converts Arabic-indic digits to ASCII", () => {
    expect(toEnglishDigits("٠٩١٢٣")).toBe("09123")
  })

  test("round-trips through toPersianDigits", () => {
    const original = "09123456789"
    expect(toEnglishDigits(toPersianDigits(original))).toBe(original)
  })
})

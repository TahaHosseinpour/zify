import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
const ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

// A phone-number `<input type="tel">` on a Persian/Arabic keyboard layout
// produces Persian or Arabic-indic digit characters, which are byte-distinct
// from ASCII "0"-"9". `mobile` is looked up with an exact match against the
// ASCII digits stored in the database, so an un-normalized value silently
// fails to find the user — same generic "wrong number or password" error as
// an actually-wrong credential. Normalize before any lookup or storage.
export function toPersianDigits(input: string): string {
  return input.replace(/[0-9]/g, (ch) => PERSIAN_DIGITS[Number(ch)])
}

export function toEnglishDigits(input: string): string {
  return input.replace(/[۰-۹٠-٩]/g, (ch) => {
    const persianIndex = PERSIAN_DIGITS.indexOf(ch)
    if (persianIndex !== -1) return String(persianIndex)
    return String(ARABIC_INDIC_DIGITS.indexOf(ch))
  })
}

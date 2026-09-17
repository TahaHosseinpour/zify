import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { setSession } from "@/lib/auth"
import { toEnglishDigits } from "@/lib/utils"
import { checkRateLimit, peekRateLimit } from "@/lib/rate-limit"

// A 6-digit OTP (900,000 combinations) is only actually hard to guess if
// attempts are capped - unlimited tries turns it into a 10-minute brute-force
// window. Counts failures only (see below), so a real user who happens to
// mistype once never gets blocked.
const VERIFY_WINDOW_MS = 10 * 60 * 1000
const VERIFY_MAX_ATTEMPTS = 5

export async function POST(req: NextRequest) {
  const body = await req.json()
  const mobile = typeof body.mobile === "string" ? toEnglishDigits(body.mobile) : body.mobile
  const otp = typeof body.otp === "string" ? toEnglishDigits(body.otp) : body.otp

  const rateLimitKey = `verify-otp:${mobile}`
  if (peekRateLimit(rateLimitKey, VERIFY_MAX_ATTEMPTS, VERIFY_WINDOW_MS)) {
    return NextResponse.json(
      { error: "تعداد تلاش‌های ناموفق بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  const user = await prisma.user.findUnique({ where: { mobile } })
  if (!user || !user.otp || !user.otpExpiry) {
    checkRateLimit(rateLimitKey, VERIFY_MAX_ATTEMPTS, VERIFY_WINDOW_MS)
    return NextResponse.json({ error: "کاربر یافت نشد" }, { status: 400 })
  }

  if (user.otp !== otp || user.otpExpiry < new Date()) {
    checkRateLimit(rateLimitKey, VERIFY_MAX_ATTEMPTS, VERIFY_WINDOW_MS)
    return NextResponse.json({ error: "کد وارد شده اشتباه یا منقضی شده است" }, { status: 400 })
  }

  const isNewUser = !user.isVerified

  await prisma.user.update({
    where: { id: user.id },
    data: { isVerified: true, otp: null, otpExpiry: null },
  })

  await setSession({ userId: user.id, mobile: user.mobile })

  return NextResponse.json({ ok: true, isNewUser: isNewUser || !user.onboardingCompleted })
}

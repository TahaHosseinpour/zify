import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { setSession } from "@/lib/auth"
import { verifyPassword } from "@/lib/password"
import { toEnglishDigits } from "@/lib/utils"
import { checkRateLimit, peekRateLimit } from "@/lib/rate-limit"

// Counts failures only, same reasoning as verify-otp - a real user typing
// their real password once is never blocked by this.
const LOGIN_WINDOW_MS = 10 * 60 * 1000
const LOGIN_MAX_ATTEMPTS = 5

export async function POST(req: NextRequest) {
  const body = await req.json()
  const mobile = typeof body.mobile === "string" ? toEnglishDigits(body.mobile) : body.mobile
  const { password } = body

  if (!mobile || !password) {
    return NextResponse.json({ error: "شماره موبایل و رمز عبور را وارد کنید" }, { status: 400 })
  }

  const rateLimitKey = `login-password:${mobile}`
  if (peekRateLimit(rateLimitKey, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MS)) {
    return NextResponse.json(
      { error: "تعداد تلاش‌های ناموفق بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  const user = await prisma.user.findUnique({ where: { mobile } })

  // Same generic message whether the user is missing, has no password set, or
  // the password is wrong — so we don't leak which accounts exist / use passwords.
  if (!user || !user.password || !(await verifyPassword(password, user.password))) {
    checkRateLimit(rateLimitKey, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MS)
    return NextResponse.json({ error: "شماره موبایل یا رمز عبور اشتباه است" }, { status: 401 })
  }

  await setSession({ userId: user.id, mobile: user.mobile })

  return NextResponse.json({ ok: true, isNewUser: !user.onboardingCompleted })
}

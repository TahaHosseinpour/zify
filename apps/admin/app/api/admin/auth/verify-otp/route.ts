import { NextRequest, NextResponse } from "next/server"
import { consumeAdminOtp, getPendingAdmin, setAdminSession } from "@/lib/admin-auth"
import { checkRateLimit, peekRateLimit } from "@/lib/rate-limit"
import { toEnglishDigits } from "@/lib/utils"

// A 6-digit code is only hard to guess while guesses are scarce. Failures
// only, per admin: after this many the code is as good as burned, and a new
// one has to be requested (which needs the password again).
const WINDOW_MS = 15 * 60 * 1000
const MAX_ATTEMPTS = 5

/**
 * Platform admin sign-in, step two: the code sent by SMS. Only reachable by a
 * browser that passed step one - the admin is read from the pending cookie,
 * never from the request body - and only this creates the session.
 */
export async function POST(req: NextRequest) {
  const admin = await getPendingAdmin()
  if (!admin) {
    return NextResponse.json(
      { error: "مهلت این مرحله تمام شده است. دوباره با نام کاربری و رمز وارد شوید." },
      { status: 401 },
    )
  }

  const rateLimitKey = `admin-otp-verify:${admin.id}`
  if (peekRateLimit(rateLimitKey, MAX_ATTEMPTS, WINDOW_MS)) {
    return NextResponse.json(
      { error: "تعداد تلاش‌های ناموفق بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  const body = await req.json()
  const otp = typeof body.otp === "string" ? toEnglishDigits(body.otp).trim() : ""
  if (!/^\d{6}$/.test(otp) || !(await consumeAdminOtp(admin, otp))) {
    checkRateLimit(rateLimitKey, MAX_ATTEMPTS, WINDOW_MS)
    return NextResponse.json({ error: "کد وارد شده اشتباه یا منقضی شده است" }, { status: 401 })
  }

  await setAdminSession(admin.id)
  return NextResponse.json({ ok: true })
}

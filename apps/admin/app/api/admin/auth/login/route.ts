import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { maskMobile, sendAdminOtp, setAdminPending } from "@/lib/admin-auth"
import { verifyPassword } from "@/lib/password"
import { checkRateLimit, clientIp, peekRateLimit } from "@/lib/rate-limit"

// Failures only, counted per username and per address: a guessed password
// against this login is worth far more than one against a shop owner's.
const WINDOW_MS = 15 * 60 * 1000
const MAX_ATTEMPTS = 5
// Every correct password sends a real SMS, so those are capped too.
const MAX_CODES_PER_WINDOW = 5

const TOO_MANY = "تعداد تلاش‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید."

/**
 * Platform admin sign-in, step one: username and password. Success does not
 * sign anyone in - it sends a one-time code to the admin's mobile and marks
 * this browser as having passed the first step (see lib/admin-auth.ts). The
 * session is only created by /api/admin/auth/verify-otp.
 */
export async function POST(req: NextRequest) {
  const body = await req.json()
  const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : ""
  const password = typeof body.password === "string" ? body.password : ""
  if (!username || !password) {
    return NextResponse.json({ error: "نام کاربری و رمز عبور را وارد کنید" }, { status: 400 })
  }

  const keys = [`admin-login:user:${username}`, `admin-login:ip:${clientIp(req)}`]
  if (keys.some((key) => peekRateLimit(key, MAX_ATTEMPTS, WINDOW_MS))) {
    return NextResponse.json({ error: TOO_MANY }, { status: 429 })
  }

  const admin = await prisma.admin.findUnique({ where: { username } })
  // One message for every way this can fail, so the reply never reveals
  // which usernames exist or which are deactivated.
  if (!admin || !admin.isActive || !(await verifyPassword(password, admin.password))) {
    for (const key of keys) checkRateLimit(key, MAX_ATTEMPTS, WINDOW_MS)
    return NextResponse.json({ error: "نام کاربری یا رمز عبور اشتباه است" }, { status: 401 })
  }

  if (!checkRateLimit(`admin-otp-send:${admin.id}`, MAX_CODES_PER_WINDOW, WINDOW_MS).allowed) {
    return NextResponse.json({ error: TOO_MANY }, { status: 429 })
  }

  try {
    await sendAdminOtp(admin)
  } catch (err) {
    console.error("[admin-login] sending the code failed:", err)
    return NextResponse.json({ error: "ارسال کد تایید ناموفق بود. دوباره تلاش کنید." }, { status: 502 })
  }

  await setAdminPending(admin.id)
  return NextResponse.json({ ok: true, mobile: maskMobile(admin.mobile) })
}

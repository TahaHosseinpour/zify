import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { setAdminSession } from "@/lib/admin-auth"
import { verifyPassword } from "@/lib/password"
import { checkRateLimit, clientIp, peekRateLimit } from "@/lib/rate-limit"

// Failures only, counted per username and per address: a guessed password
// against this login is worth far more than one against a shop owner's.
const WINDOW_MS = 15 * 60 * 1000
const MAX_ATTEMPTS = 5

const TOO_MANY = "تعداد تلاش‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید."

/** Platform admin sign-in: username and password create the session. */
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

  await setAdminSession(admin.id)
  return NextResponse.json({ ok: true })
}

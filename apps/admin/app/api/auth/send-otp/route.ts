import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { sendOtp } from "@/lib/sms"
import { toEnglishDigits } from "@/lib/utils"
import { checkRateLimit, clientIp } from "@/lib/rate-limit"

// Unauthenticated by design (you don't have a session yet when requesting an
// OTP), so this is the one endpoint in the app anyone can hit with no login
// at all - without a cap, it's both a free way to drain SMS credit and a way
// to SMS-bomb an arbitrary phone number with verification texts that were
// never asked for.
const OTP_WINDOW_MS = 10 * 60 * 1000
const OTP_MAX_PER_MOBILE = 3
const OTP_MAX_PER_IP = 10

export async function POST(req: NextRequest) {
  const body = await req.json()
  const mobile = typeof body.mobile === "string" ? toEnglishDigits(body.mobile) : body.mobile
  if (!mobile || mobile.length < 10) {
    return NextResponse.json({ error: "شماره موبایل معتبر نیست" }, { status: 400 })
  }

  const ip = clientIp(req)
  const perMobile = checkRateLimit(`otp:${mobile}`, OTP_MAX_PER_MOBILE, OTP_WINDOW_MS)
  const perIp = checkRateLimit(`otp-ip:${ip}`, OTP_MAX_PER_IP, OTP_WINDOW_MS)
  if (!perMobile.allowed || !perIp.allowed) {
    return NextResponse.json(
      { error: "تعداد درخواست‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  const otp = await sendOtp(mobile)
  const otpExpiry = new Date(Date.now() + 10 * 60 * 1000)

  await prisma.user.upsert({
    where: { mobile },
    update: { otp, otpExpiry },
    create: { mobile, otp, otpExpiry },
  })

  return NextResponse.json({ ok: true })
}

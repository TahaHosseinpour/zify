import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { sendOtp } from "@/lib/sms"
import { toEnglishDigits } from "@/lib/utils"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const mobile = typeof body.mobile === "string" ? toEnglishDigits(body.mobile) : body.mobile
  if (!mobile || mobile.length < 10) {
    return NextResponse.json({ error: "شماره موبایل معتبر نیست" }, { status: 400 })
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

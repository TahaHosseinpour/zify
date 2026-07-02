import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { sendOtp } from "@/lib/sms"

export async function POST(req: NextRequest) {
  const { mobile } = await req.json()
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

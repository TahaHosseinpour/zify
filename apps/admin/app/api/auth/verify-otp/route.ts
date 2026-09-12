import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { setSession } from "@/lib/auth"
import { toEnglishDigits } from "@/lib/utils"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const mobile = typeof body.mobile === "string" ? toEnglishDigits(body.mobile) : body.mobile
  const otp = typeof body.otp === "string" ? toEnglishDigits(body.otp) : body.otp

  const user = await prisma.user.findUnique({ where: { mobile } })
  if (!user || !user.otp || !user.otpExpiry) {
    return NextResponse.json({ error: "کاربر یافت نشد" }, { status: 400 })
  }

  if (user.otp !== otp || user.otpExpiry < new Date()) {
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

import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { setSession } from "@/lib/auth"
import { verifyPassword } from "@/lib/password"

export async function POST(req: NextRequest) {
  const { mobile, password } = await req.json()

  if (!mobile || !password) {
    return NextResponse.json({ error: "شماره موبایل و رمز عبور را وارد کنید" }, { status: 400 })
  }

  const user = await prisma.user.findUnique({ where: { mobile } })

  // Same generic message whether the user is missing, has no password set, or
  // the password is wrong — so we don't leak which accounts exist / use passwords.
  if (!user || !user.password || !(await verifyPassword(password, user.password))) {
    return NextResponse.json({ error: "شماره موبایل یا رمز عبور اشتباه است" }, { status: 401 })
  }

  await setSession({ userId: user.id, mobile: user.mobile })

  return NextResponse.json({ ok: true, isNewUser: !user.onboardingCompleted })
}

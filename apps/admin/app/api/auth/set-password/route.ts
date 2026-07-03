import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { getSession } from "@/lib/auth"
import { hashPassword } from "@/lib/password"

export async function POST(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت نشده" }, { status: 401 })

  const { password } = await req.json()
  if (!password || typeof password !== "string" || password.length < 6) {
    return NextResponse.json({ error: "رمز عبور باید حداقل ۶ کاراکتر باشد" }, { status: 400 })
  }

  await prisma.user.update({
    where: { id: session.userId },
    data: { password: await hashPassword(password) },
  })

  return NextResponse.json({ ok: true })
}

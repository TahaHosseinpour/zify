import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

export async function POST() {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  await prisma.user.update({
    where: { id: session.userId },
    data: { onboardingCompleted: true },
  })

  return NextResponse.json({ ok: true })
}

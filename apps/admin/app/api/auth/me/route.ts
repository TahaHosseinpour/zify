import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json(null, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    select: { id: true, mobile: true, fullName: true, isVerified: true, onboardingCompleted: true, password: true },
  })

  if (!user) return NextResponse.json(null, { status: 401 })

  // Expose only whether a password exists, never the hash itself.
  const { password, ...rest } = user
  return NextResponse.json({ ...rest, hasPassword: Boolean(password) })
}

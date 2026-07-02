import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json([], { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json([])

  const conversations = await prisma.conversation.findMany({
    where: { shopId: shop.id },
    orderBy: { startedAt: "desc" },
    take: 100,
    include: {
      endUser: { select: { firstName: true, username: true } },
      _count: { select: { messages: true } },
    },
  })

  return NextResponse.json(conversations)
}

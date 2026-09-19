import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma, PLAYGROUND_WEB_VISITOR_ID } from "@zify/db"

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
    // The shop owner's own test sessions (آزمایشگاه فروش) live under a
    // sentinel EndUser and don't belong in a list of real customer chats.
    where: { shopId: shop.id, endUser: { webVisitorId: { not: PLAYGROUND_WEB_VISITOR_ID } } },
    orderBy: { startedAt: "desc" },
    take: 100,
    include: {
      endUser: { select: { firstName: true, username: true } },
      _count: { select: { messages: true } },
    },
  })

  return NextResponse.json(conversations)
}

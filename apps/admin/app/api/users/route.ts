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

  const endUsers = await prisma.endUser.findMany({
    // Excludes the sentinel EndUser behind آزمایشگاه فروش (see chats/route.ts) —
    // the shop owner testing their own bot isn't a customer.
    where: { shopId: shop.id, webVisitorId: { not: PLAYGROUND_WEB_VISITOR_ID } },
    orderBy: { createdAt: "desc" },
    include: { _count: { select: { conversations: true } } },
  })

  return NextResponse.json(endUsers)
}

import { NextRequest, NextResponse } from "next/server"
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

/** Block or unblock one of this shop's customers. A blocked customer gets
 * the same "assistant is off" reply as anyone would if the shop had no
 * subscription (packages/db/src/billing.ts) - the owner's own control over a
 * customer who is wasting their conversations. */
export async function PATCH(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const body = await req.json()
  const id = typeof body.id === "string" ? body.id : ""
  if (!id || typeof body.isBlocked !== "boolean") {
    return NextResponse.json({ error: "اطلاعات ناقص است" }, { status: 400 })
  }

  // updateMany so the shop scope is part of the write itself: an id from
  // another shop matches nothing rather than being updated.
  const result = await prisma.endUser.updateMany({
    where: { id, shopId: shop.id },
    data: { isBlocked: body.isBlocked },
  })
  if (result.count === 0) return NextResponse.json({ error: "کاربر یافت نشد" }, { status: 404 })
  return NextResponse.json({ ok: true })
}

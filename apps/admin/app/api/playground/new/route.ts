import { NextResponse } from "next/server"
import { prisma, startNewConversation, PLAYGROUND_WEB_VISITOR_ID } from "@zify/db"
import { resolvePlaygroundShop } from "@/lib/resolve-playground"

/** Authenticated counterpart to /api/shop-chat/new - "چت جدید" in آزمایشگاه
 * فروش, scoped to the shop owner's own sentinel EndUser. */
export async function POST() {
  const shop = await resolvePlaygroundShop()
  if (!shop) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const endUser = await prisma.endUser.upsert({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId: PLAYGROUND_WEB_VISITOR_ID } },
    update: {},
    create: { shopId: shop.id, webVisitorId: PLAYGROUND_WEB_VISITOR_ID },
  })

  const conversation = await startNewConversation(shop.id, endUser.id)
  return NextResponse.json({ ok: true, conversationId: conversation.id })
}

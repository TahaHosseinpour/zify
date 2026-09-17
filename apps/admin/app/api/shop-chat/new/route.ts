import { NextRequest, NextResponse } from "next/server"
import { prisma, startNewConversation } from "@zify/db"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const slug = typeof body.slug === "string" ? body.slug : ""
  const webVisitorId = typeof body.webVisitorId === "string" ? body.webVisitorId : ""
  if (!slug || !webVisitorId) {
    return NextResponse.json({ error: "اطلاعات ناقص است" }, { status: 400 })
  }

  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  // A "new chat" click before this visitor has ever sent a message yet
  // simply has nothing to start over from - upsert the same as the main
  // chat route does, so the button always works.
  const endUser = await prisma.endUser.upsert({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId } },
    update: {},
    create: { shopId: shop.id, webVisitorId },
  })

  const conversation = await startNewConversation(shop.id, endUser.id)
  return NextResponse.json({ ok: true, conversationId: conversation.id })
}

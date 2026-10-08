import { NextRequest, NextResponse } from "next/server"
import { prisma, startNewConversation } from "@zify/db"
import { readVisitorId } from "@/lib/visitor-cookie"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const slug = typeof body.slug === "string" ? body.slug : ""
  if (!slug) return NextResponse.json({ error: "اطلاعات ناقص است" }, { status: 400 })

  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  // A "new chat" click before this visitor has ever sent a message has
  // nothing to start over from: identities are only issued by the chat route
  // itself (where issuing them is rate-limited), so there is no one to start
  // a conversation for yet. The next message opens one anyway.
  const webVisitorId = readVisitorId(req)
  const endUser = webVisitorId
    ? await prisma.endUser.findUnique({
        where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId } },
      })
    : null
  if (!endUser) return NextResponse.json({ ok: true, conversationId: null })

  const conversation = await startNewConversation(shop.id, endUser.id)
  return NextResponse.json({ ok: true, conversationId: conversation.id })
}

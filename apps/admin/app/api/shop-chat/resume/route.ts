import { NextRequest, NextResponse } from "next/server"
import { prisma, resumeConversation } from "@zify/db"
import { resolveShopVisitor } from "@/lib/resolve-shop-visitor"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const slug = typeof body.slug === "string" ? body.slug : ""
  const webVisitorId = typeof body.webVisitorId === "string" ? body.webVisitorId : ""
  const conversationId = typeof body.conversationId === "string" ? body.conversationId : ""
  if (!slug || !webVisitorId || !conversationId) {
    return NextResponse.json({ error: "اطلاعات ناقص است" }, { status: 400 })
  }

  const resolved = await resolveShopVisitor(slug, webVisitorId)
  if (!resolved?.endUser) return NextResponse.json({ error: "یافت نشد" }, { status: 404 })

  const conversation = await resumeConversation(resolved.shop.id, resolved.endUser.id, conversationId)
  if (!conversation) return NextResponse.json({ error: "این گفتگو یافت نشد" }, { status: 404 })

  // The client shows the resumed conversation's past messages, not a blank
  // slate that silently continues in the background.
  const messages = await prisma.message.findMany({
    where: { conversationId: conversation.id },
    orderBy: { createdAt: "asc" },
  })

  return NextResponse.json({
    ok: true,
    conversationId: conversation.id,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
  })
}

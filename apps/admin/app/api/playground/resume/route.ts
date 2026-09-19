import { NextRequest, NextResponse } from "next/server"
import { prisma, resumeConversation } from "@zify/db"
import { resolvePlaygroundVisitor } from "@/lib/resolve-playground"

/** Authenticated counterpart to /api/shop-chat/resume - clicking a past
 * session in آزمایشگاه فروش's "چت‌های قبلی" list. */
export async function POST(req: NextRequest) {
  const body = await req.json()
  const conversationId = typeof body.conversationId === "string" ? body.conversationId : ""
  if (!conversationId) return NextResponse.json({ error: "اطلاعات ناقص است" }, { status: 400 })

  const resolved = await resolvePlaygroundVisitor()
  if (!resolved?.endUser) return NextResponse.json({ error: "یافت نشد" }, { status: 404 })

  const conversation = await resumeConversation(resolved.shop.id, resolved.endUser.id, conversationId)
  if (!conversation) return NextResponse.json({ error: "این گفتگو یافت نشد" }, { status: 404 })

  const messages = await prisma.message.findMany({
    where: { conversationId: conversation.id },
    orderBy: { createdAt: "asc" },
  })

  return NextResponse.json({
    ok: true,
    conversationId: conversation.id,
    mode: conversation.mode,
    productId: conversation.productId,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
  })
}

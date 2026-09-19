import { NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { resolvePlaygroundVisitor } from "@/lib/resolve-playground"

/** Authenticated counterpart to /api/shop-chat/history - the "چت‌های قبلی"
 * list in آزمایشگاه فروش, scoped to the shop owner's own sentinel EndUser. */
export async function GET() {
  const resolved = await resolvePlaygroundVisitor()
  if (!resolved) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })
  if (!resolved.endUser) return NextResponse.json([])

  const conversations = await prisma.conversation.findMany({
    where: { shopId: resolved.shop.id, endUserId: resolved.endUser.id },
    orderBy: { lastMessageAt: "desc" },
    take: 20,
    include: { messages: { orderBy: { createdAt: "asc" }, take: 1 } },
  })

  return NextResponse.json(
    conversations.map((c) => ({
      id: c.id,
      startedAt: c.startedAt,
      lastMessageAt: c.lastMessageAt,
      preview: c.messages[0]?.content?.slice(0, 60) ?? null,
    })),
  )
}

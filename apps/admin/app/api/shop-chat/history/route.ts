import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { resolveShopVisitor } from "@/lib/resolve-shop-visitor"
import { readVisitorId } from "@/lib/visitor-cookie"

export async function GET(req: NextRequest) {
  const slug = req.nextUrl.searchParams.get("slug") ?? ""
  if (!slug) return NextResponse.json({ error: "slug الزامی است" }, { status: 400 })
  // No signed cookie yet means no identity yet: resolves to "never chatted".
  const webVisitorId = readVisitorId(req) ?? ""

  const resolved = await resolveShopVisitor(slug, webVisitorId)
  if (!resolved) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })
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

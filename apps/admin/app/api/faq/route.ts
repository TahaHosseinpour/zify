import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedFaq } from "@/lib/embeddings"

async function getShop(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json([], { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json([])

  const items = await prisma.faqItem.findMany({
    where: { shopId: shop.id },
    orderBy: { id: "asc" },
  })

  return NextResponse.json(items)
}

export async function POST(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const { question, answer } = await req.json()
  if (!question || !answer) {
    return NextResponse.json({ error: "سوال و پاسخ الزامی است" }, { status: 400 })
  }

  const item = await prisma.faqItem.create({
    data: { shopId: shop.id, question, answer },
  })

  embedFaq(item.id, question).catch(() => {})

  return NextResponse.json(item)
}

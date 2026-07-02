import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma, type Channel } from "@zify/db"

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

  const channels = await prisma.channel.findMany({
    where: { shopId: shop.id },
    orderBy: { createdAt: "desc" },
  })

  const botUsername = process.env.BOT_USERNAME || "ZifyBot"
  return NextResponse.json(
    channels.map((ch: Channel) => ({
      ...ch,
      deepLink: `https://t.me/${botUsername}?start=${shop.slug}`,
      exploreLink: `https://t.me/${botUsername}?start=${shop.slug}`,
    }))
  )
}

export async function POST(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const channel = await prisma.channel.create({
    data: { shopId: shop.id, type: "telegram" },
  })

  const botUsername = process.env.BOT_USERNAME || "ZifyBot"
  return NextResponse.json({
    ...channel,
    deepLink: `https://t.me/${botUsername}?start=${shop.slug}`,
  })
}

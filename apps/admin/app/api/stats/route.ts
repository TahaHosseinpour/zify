import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

function dateRange(days: number) {
  const now = new Date()
  const from = new Date(now)
  from.setDate(from.getDate() - days + 1)
  from.setHours(0, 0, 0, 0)
  return from
}

function groupByDate(
  items: { createdAt: Date }[]
): { date: string; count: number }[] {
  const map: Record<string, number> = {}
  for (const item of items) {
    const key = item.createdAt.toISOString().slice(0, 10)
    map[key] = (map[key] ?? 0) + 1
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, count }))
}

export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json(null, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) {
    return NextResponse.json({
      totalUsers: 0,
      totalMessages: 0,
      totalClicks: 0,
      totalOrders: 0,
      totalRevenue: 0,
      timeSaved: 0,
      dailyMessages: [],
      dailyUsers: [],
      dailyClicks: [],
    })
  }

  const since30 = dateRange(30)

  const [totalUsers, totalOrders, orders, recentMessages, recentUsers, recentClicks, allClicks] =
    await Promise.all([
      prisma.endUser.count({ where: { shopId: shop.id } }),
      prisma.order.count({ where: { shopId: shop.id } }),
      prisma.order.findMany({ where: { shopId: shop.id }, select: { amount: true } }),
      prisma.event.findMany({
        where: { shopId: shop.id, type: "message", createdAt: { gte: since30 } },
        select: { createdAt: true },
      }),
      prisma.endUser.findMany({
        where: { shopId: shop.id, createdAt: { gte: since30 } },
        select: { createdAt: true },
      }),
      prisma.event.findMany({
        where: { shopId: shop.id, type: "click", createdAt: { gte: since30 } },
        select: { createdAt: true },
      }),
      prisma.event.count({ where: { shopId: shop.id, type: "click" } }),
    ])

  const totalRevenue = orders.reduce((sum: number, o: { amount: unknown }) => sum + Number(o.amount), 0)
  const totalMessages = await prisma.event.count({ where: { shopId: shop.id, type: "message" } })

  return NextResponse.json({
    totalUsers,
    totalMessages,
    totalClicks: allClicks,
    totalOrders,
    totalRevenue,
    timeSaved: Math.round(totalMessages * 2),
    dailyMessages: groupByDate(recentMessages),
    dailyUsers: groupByDate(recentUsers),
    dailyClicks: groupByDate(recentClicks),
  })
}

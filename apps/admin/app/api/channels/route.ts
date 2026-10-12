import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma, isChannelActive, isChannelType, setChannelActive } from "@zify/db"

async function getShop(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

function telegramLink(slug: string): string {
  const botUsername = process.env.BOT_USERNAME || "ZifyBot"
  return `https://t.me/${botUsername}?start=${slug}`
}

/** Which channels this shop has switched on. */
export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json(null, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json(null, { status: 404 })

  const [telegram, widget] = await Promise.all([
    isChannelActive(shop.id, "telegram"),
    isChannelActive(shop.id, "widget"),
  ])
  return NextResponse.json({
    slug: shop.slug,
    telegram: { active: telegram, link: telegramLink(shop.slug) },
    widget: { active: widget },
  })
}

/** Switch one channel on or off: `{ type: "telegram" | "widget", active }`. */
export async function PUT(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const body = await req.json()
  if (!isChannelType(body.type) || typeof body.active !== "boolean") {
    return NextResponse.json({ error: "درخواست نامعتبر است" }, { status: 400 })
  }

  await setChannelActive(shop.id, body.type, body.active)
  return NextResponse.json({ ok: true, type: body.type, active: body.active })
}

/** Onboarding's "connect Telegram" step: switches Telegram on and returns the
 * shop's link. */
export async function POST() {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  await setChannelActive(shop.id, "telegram", true)
  return NextResponse.json({ deepLink: telegramLink(shop.slug) })
}

import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

async function getShop(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const { id } = await params
  const channel = await prisma.channel.findUnique({ where: { id } })
  if (!channel || channel.shopId !== shop.id) {
    return NextResponse.json({ error: "کانال یافت نشد" }, { status: 404 })
  }

  await prisma.channel.delete({ where: { id } })

  return NextResponse.json({ ok: true })
}

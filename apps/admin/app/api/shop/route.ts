import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { rebuildShopInfoChunks } from "@/lib/embeddings"

export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json(null, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })

  return NextResponse.json(user?.shops[0] ?? null)
}

export async function POST(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const body = await req.json()
  const { name, slug, description, categories, supportInfo, personaCharacter, personaTone, systemPromptExtra } = body

  if (!name || !slug) {
    return NextResponse.json({ error: "نام و شناسه فروشگاه الزامی است" }, { status: 400 })
  }

  const existing = await prisma.shop.findUnique({ where: { slug } })
  if (existing) {
    return NextResponse.json({ error: "این شناسه قبلاً استفاده شده است" }, { status: 400 })
  }

  const shop = await prisma.shop.create({
    data: {
      name,
      slug,
      description,
      categories: categories ?? [],
      supportInfo,
      personaCharacter,
      personaTone,
      systemPromptExtra,
      ownerId: session.userId,
    },
  })

  await rebuildShopInfoChunks(shop.id).catch(() => {})

  return NextResponse.json(shop)
}

export async function PATCH(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const body = await req.json()
  const { name, description, categories, supportInfo, personaCharacter, personaTone, systemPromptExtra } = body

  const updated = await prisma.shop.update({
    where: { id: shop.id },
    data: {
      ...(name !== undefined && { name }),
      ...(description !== undefined && { description }),
      ...(categories !== undefined && { categories }),
      ...(supportInfo !== undefined && { supportInfo }),
      ...(personaCharacter !== undefined && { personaCharacter }),
      ...(personaTone !== undefined && { personaTone }),
      ...(systemPromptExtra !== undefined && { systemPromptExtra }),
    },
  })

  await rebuildShopInfoChunks(shop.id).catch(() => {})

  return NextResponse.json(updated)
}

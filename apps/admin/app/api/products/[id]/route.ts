import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedProduct } from "@/lib/embeddings"
import { checkAndRecordProductEdit } from "@/lib/product-limits"

async function getShop(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const { id } = await params
  const existing = await prisma.product.findUnique({ where: { id } })
  if (!existing || existing.shopId !== shop.id) {
    return NextResponse.json({ error: "محصول یافت نشد" }, { status: 404 })
  }

  const limitCheck = await checkAndRecordProductEdit(shop.id)
  if (!limitCheck.ok) {
    const message = `سقف ماهانه افزودن/ویرایش محصول (${limitCheck.limit.toLocaleString("fa-IR")} مورد) پر شده است. ماه بعد دوباره امکان‌پذیر خواهد بود.`
    return NextResponse.json({ error: message }, { status: 429 })
  }

  const body = await req.json()
  const { name, price, description, productUrl, imageUrl, isActive, category, brand } = body

  const product = await prisma.product.update({
    where: { id },
    data: {
      ...(name !== undefined && { name }),
      ...(price !== undefined && { price }),
      ...(description !== undefined && { description }),
      ...(productUrl !== undefined && { productUrl }),
      ...(imageUrl !== undefined && { imageUrl }),
      ...(isActive !== undefined && { isActive }),
      ...(category !== undefined && { category: category || null }),
      ...(brand !== undefined && { brand: brand || null }),
    },
  })

  const embedText = [product.name, product.description, product.category, product.brand]
    .filter(Boolean)
    .join(" ")
  embedProduct(product.id, embedText).catch(() => {})

  return NextResponse.json(product)
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const { id } = await params
  const existing = await prisma.product.findUnique({ where: { id } })
  if (!existing || existing.shopId !== shop.id) {
    return NextResponse.json({ error: "محصول یافت نشد" }, { status: 404 })
  }

  await prisma.product.delete({ where: { id } })

  return NextResponse.json({ ok: true })
}

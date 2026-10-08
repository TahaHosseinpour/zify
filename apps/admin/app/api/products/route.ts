import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedProduct } from "@/lib/embeddings"
import { checkAndRecordProductUpload } from "@/lib/product-limits"

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

  const products = await prisma.product.findMany({
    where: { shopId: shop.id },
    orderBy: { createdAt: "desc" },
  })

  return NextResponse.json(products)
}

export async function POST(req: NextRequest) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const body = await req.json()
  const { name, price, description, productUrl, imageUrl, category, brand } = body

  if (!name || price === undefined) {
    return NextResponse.json({ error: "نام و قیمت الزامی است" }, { status: 400 })
  }

  const limitCheck = await checkAndRecordProductUpload(shop.id)
  if (!limitCheck.ok) {
    const message =
      limitCheck.reason === "active_cap"
        ? `سقف ${limitCheck.limit.toLocaleString("fa-IR")} محصول فعال اشتراک شما پر شده است. برای افزودن محصول جدید، ابتدا یکی از محصولات فعلی را حذف یا غیرفعال کنید.`
        : `سقف ماهانه افزودن محصول (${limitCheck.limit.toLocaleString("fa-IR")} مورد) پر شده است. ماه بعد دوباره امکان‌پذیر خواهد بود.`
    return NextResponse.json({ error: message }, { status: 429 })
  }

  const product = await prisma.product.create({
    data: {
      shopId: shop.id,
      name,
      price,
      description,
      productUrl,
      imageUrl,
      category: category || null,
      brand: brand || null,
    },
  })

  // category/brand are part of the embedded text so the vector step ranks on
  // the same signal the SQL step filters on.
  const embedText = [name, description, category, brand].filter(Boolean).join(" ")
  embedProduct(product.id, embedText).catch(() => {})

  return NextResponse.json(product)
}

export async function DELETE() {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const { count } = await prisma.product.deleteMany({ where: { shopId: shop.id } })

  return NextResponse.json({ ok: true, count })
}

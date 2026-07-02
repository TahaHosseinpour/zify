import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedProduct } from "@/lib/embeddings"

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
  const { name, price, description, productUrl, imageUrl } = body

  if (!name || price === undefined) {
    return NextResponse.json({ error: "نام و قیمت الزامی است" }, { status: 400 })
  }

  const product = await prisma.product.create({
    data: {
      shopId: shop.id,
      name,
      price,
      description,
      productUrl,
      imageUrl,
    },
  })

  const embedText = [name, description].filter(Boolean).join(" ")
  embedProduct(product.id, embedText).catch(() => {})

  return NextResponse.json(product)
}

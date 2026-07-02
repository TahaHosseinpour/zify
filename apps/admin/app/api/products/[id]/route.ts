import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedProduct } from "@/lib/embeddings"

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const { id } = await params
  const body = await req.json()
  const { name, price, description, productUrl, imageUrl, isActive } = body

  const product = await prisma.product.update({
    where: { id },
    data: {
      ...(name !== undefined && { name }),
      ...(price !== undefined && { price }),
      ...(description !== undefined && { description }),
      ...(productUrl !== undefined && { productUrl }),
      ...(imageUrl !== undefined && { imageUrl }),
      ...(isActive !== undefined && { isActive }),
    },
  })

  const embedText = [product.name, product.description]
    .filter(Boolean)
    .join(" ")
  embedProduct(product.id, embedText).catch(() => {})

  return NextResponse.json(product)
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const { id } = await params
  await prisma.product.delete({ where: { id } })

  return NextResponse.json({ ok: true })
}

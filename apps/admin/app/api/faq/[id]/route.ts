import { NextRequest, NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { embedFaq } from "@/lib/embeddings"

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const { id } = await params
  const { question, answer } = await req.json()

  const item = await prisma.faqItem.update({
    where: { id },
    data: {
      ...(question !== undefined && { question }),
      ...(answer !== undefined && { answer }),
    },
  })

  embedFaq(item.id, item.question).catch(() => {})

  return NextResponse.json(item)
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const { id } = await params
  await prisma.faqItem.delete({ where: { id } })

  return NextResponse.json({ ok: true })
}

import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:3001"

export async function POST(request: Request) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const body = await request.json()
  const message = typeof body.message === "string" ? body.message.trim() : ""
  const sessionId = typeof body.sessionId === "string" ? body.sessionId : ""

  if (!message) return NextResponse.json({ error: "پیام خالی است" }, { status: 400 })
  if (!sessionId) return NextResponse.json({ error: "شناسه گفت‌وگو لازم است" }, { status: 400 })

  // Same "<shopId>:<endUserId>" shape the Telegram bot uses, so the playground
  // gets its own isolated memory and is still wiped by "ریست حافظه دستیار".
  const threadId = `${shop.id}:playground-${sessionId}`

  try {
    const res = await fetch(`${AGENT_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shopId: shop.id,
        threadId,
        message,
        mode: body.mode ?? "explore",
        productId: body.productId ?? null,
        debug: true,
      }),
    })
    if (!res.ok) throw new Error(`agent responded ${res.status}`)
    return NextResponse.json(await res.json())
  } catch (err) {
    console.error("[admin] playground chat failed:", err)
    return NextResponse.json(
      { error: "سرویس دستیار در دسترس نیست" },
      { status: 502 },
    )
  }
}

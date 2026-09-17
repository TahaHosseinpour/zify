import { NextRequest, NextResponse } from "next/server"
import { prisma, getOrStartConversation } from "@zify/db"
import { parseSseEvents } from "@/lib/sse"

const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:3001"

/**
 * Public (unauthenticated by design - this is the storefront, anyone
 * browsing it is a visitor, not a logged-in shop owner), streaming proxy to
 * the agent's /chat/stream for the /shops/[slug]/chat UI. Mirrors what the
 * Telegram bot does around each turn (getOrStartConversation, persisting
 * both messages, carrying mode/productId forward) but relays the SSE stream
 * straight through to the browser instead of waiting for a full reply -
 * `ReadableStream.tee()` splits the agent's response so the browser sees it
 * live while a second, untapped copy is consumed here afterwards to persist
 * the finished reply without adding latency to the stream itself.
 */
export async function POST(req: NextRequest) {
  const body = await req.json()
  const slug = typeof body.slug === "string" ? body.slug : ""
  const webVisitorId = typeof body.webVisitorId === "string" ? body.webVisitorId : ""
  const message = typeof body.message === "string" ? body.message.trim() : ""
  const mode = body.mode === "product" ? "product" : "explore"
  const productId = typeof body.productId === "string" ? body.productId : undefined

  if (!slug || !webVisitorId || !message) {
    return NextResponse.json({ error: "slug, webVisitorId, message الزامی است" }, { status: 400 })
  }

  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  const endUser = await prisma.endUser.upsert({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId } },
    update: {},
    create: { shopId: shop.id, webVisitorId },
  })

  const conversation = await getOrStartConversation(shop.id, endUser.id, mode, productId)
  const threadId = `${shop.id}:${endUser.id}:${conversation.id}`

  await prisma.message.create({
    data: { conversationId: conversation.id, role: "user", content: message },
  })

  let agentRes: Response
  try {
    agentRes = await fetch(`${AGENT_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shopId: shop.id,
        endUserId: endUser.id,
        mode: conversation.mode,
        productId: conversation.productId,
        threadId,
        message,
      }),
    })
  } catch (err) {
    console.error("[shop-chat] agent unreachable:", err)
    return NextResponse.json({ error: "سرویس دستیار در دسترس نیست" }, { status: 502 })
  }

  if (!agentRes.ok || !agentRes.body) {
    return NextResponse.json({ error: "سرویس دستیار در دسترس نیست" }, { status: 502 })
  }

  const [browserStream, persistStream] = agentRes.body.tee()

  // Fire-and-forget: reconstruct the reply from the "answer" chunks and
  // apply "done"'s mode/productId, same bookkeeping the bot does after every
  // turn. Never blocks or fails the response the browser is already reading.
  ;(async () => {
    try {
      const text = await new Response(persistStream).text()
      const events = parseSseEvents(text)
      const reply = events
        .filter((e) => e.event === "answer")
        .map((e) => (e.data as { text?: string })?.text ?? "")
        .join("")
      const done = events.find((e) => e.event === "done")?.data as
        | { mode?: string; productId?: string | null }
        | undefined

      if (reply) {
        await prisma.message.create({
          data: { conversationId: conversation.id, role: "assistant", content: reply },
        })
      }

      if (done) {
        const nextMode = done.mode ?? conversation.mode
        const nextProductId = done.productId ?? null
        if (nextMode !== conversation.mode || nextProductId !== conversation.productId) {
          await prisma.conversation.update({
            where: { id: conversation.id },
            data: { mode: nextMode, productId: nextProductId },
          })
        }
      }
    } catch (err) {
      console.error("[shop-chat] post-turn persistence failed:", err)
    }
  })()

  return new Response(browserStream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // So the client can highlight this conversation in the history sidebar
      // without a second round trip - the SSE body itself has no room for a
      // side-channel field like this (it's the agent's own response, relayed
      // verbatim).
      "X-Conversation-Id": conversation.id,
    },
  })
}

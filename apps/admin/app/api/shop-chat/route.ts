import { NextRequest, NextResponse } from "next/server"
import { prisma, admitTurn, PLAYGROUND_WEB_VISITOR_ID } from "@zify/db"
import { parseSseEvents, sseTextResponse } from "@/lib/sse"
import { AGENT_URL, agentHeaders } from "@/lib/agent"
import { checkRateLimit, clientIp } from "@/lib/rate-limit"
import { newVisitorId, readVisitorId, visitorCookieHeader } from "@/lib/visitor-cookie"

// Per-IP ceilings in front of everything else. The per-visitor and per-shop
// limits in admitTurn are the real protection; these stop a single address
// from even getting that far at volume.
const IP_MESSAGE_WINDOW_MS = 10 * 60 * 1000
const IP_MAX_MESSAGES = 30
// A new visitor id is a new customer with a fresh allowance, so how many one
// address can obtain is capped separately - and far lower.
const IP_NEW_VISITOR_WINDOW_MS = 60 * 60 * 1000
const IP_MAX_NEW_VISITORS = 5

const SLOW_DOWN = "تعداد پیام‌ها بیش از حد مجاز است. لطفاً چند دقیقه بعد دوباره تلاش کنید."

/**
 * Public (unauthenticated by design - this is the storefront, anyone
 * browsing it is a visitor, not a logged-in shop owner), streaming proxy to
 * the agent's /chat/stream for the /shops/[slug]/chat UI. Mirrors what the
 * Telegram bot does around each turn (admitTurn, persisting both messages,
 * carrying mode/productId forward) but relays the SSE stream straight through
 * to the browser instead of waiting for a full reply - `ReadableStream.tee()`
 * splits the agent's response so the browser sees it live while a second,
 * untapped copy is consumed here afterwards to persist the finished reply
 * without adding latency to the stream itself.
 *
 * A refusal (rate limit, no subscription, quota, message too long) is sent as
 * an ordinary one-message stream, so the chat UI shows it as the assistant's
 * reply instead of a generic error.
 */
export async function POST(req: NextRequest) {
  const body = await req.json()
  const slug = typeof body.slug === "string" ? body.slug : ""
  const message = typeof body.message === "string" ? body.message.trim() : ""
  const mode = body.mode === "product" ? "product" : "explore"
  const productId = typeof body.productId === "string" ? body.productId : undefined

  if (!slug || !message) {
    return NextResponse.json({ error: "slug و message الزامی است" }, { status: 400 })
  }

  const ip = clientIp(req)
  if (!checkRateLimit(`shop-chat:ip:${ip}`, IP_MAX_MESSAGES, IP_MESSAGE_WINDOW_MS).allowed) {
    return sseTextResponse(SLOW_DOWN)
  }

  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  // Who is this? The signed cookie, if there is one. Otherwise this browser
  // gets a new identity - or, once, keeps the one it had before ids were
  // signed, provided that id really is an existing visitor of this shop.
  const cookieVisitorId = readVisitorId(req)
  let visitorId: string
  let setCookie: string | undefined
  if (cookieVisitorId) {
    visitorId = cookieVisitorId
  } else {
    const legacyId = typeof body.webVisitorId === "string" ? body.webVisitorId : ""
    const legacy =
      legacyId && legacyId !== PLAYGROUND_WEB_VISITOR_ID
        ? await prisma.endUser.findUnique({
            where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId: legacyId } },
          })
        : null
    if (legacy) {
      visitorId = legacyId
    } else {
      const minted = checkRateLimit(
        `shop-chat:new-visitor:${ip}`,
        IP_MAX_NEW_VISITORS,
        IP_NEW_VISITOR_WINDOW_MS,
      )
      if (!minted.allowed) return sseTextResponse(SLOW_DOWN)
      visitorId = newVisitorId()
    }
    setCookie = visitorCookieHeader(visitorId)
  }
  const extraHeaders: Record<string, string> = setCookie ? { "Set-Cookie": setCookie } : {}

  const endUser = await prisma.endUser.upsert({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId: visitorId } },
    update: {},
    create: { shopId: shop.id, webVisitorId: visitorId },
  })

  const admission = await admitTurn({ shopId: shop.id, endUserId: endUser.id, message, mode, productId })
  if (!admission.ok) return sseTextResponse(admission.message, extraHeaders)

  const conversation = admission.conversation
  const threadId = `${shop.id}:${endUser.id}:${conversation.id}`

  await prisma.message.create({
    data: { conversationId: conversation.id, role: "user", content: message },
  })

  let agentRes: Response
  try {
    agentRes = await fetch(`${AGENT_URL}/chat/stream`, {
      method: "POST",
      headers: agentHeaders(),
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
      ...extraHeaders,
    },
  })
}

import { NextRequest, NextResponse } from "next/server"
import { prisma, admitTurn, PLAYGROUND_WEB_VISITOR_ID } from "@zify/db"
import { parseSseEvents, sseTextResponse } from "@/lib/sse"
import { resolvePlaygroundShop } from "@/lib/resolve-playground"
import { AGENT_URL, agentHeaders } from "@/lib/agent"

// What the shop owner sees in place of a reply when a turn is refused. Unlike
// a customer, they are told the actual reason - it is their subscription.
const OWNER_DENIAL_MESSAGES: Record<string, string> = {
  no_subscription: "اشتراک فعالی برای این فروشگاه وجود ندارد، پس دستیار خاموش است.",
  quota_exhausted: "گفتگوهای این دوره‌ی اشتراک تمام شده است.",
  shop_daily_cap: "سقف گفتگوی روزانه‌ی فروشگاه پر شده است. فردا دوباره فعال می‌شود.",
}

/**
 * Authenticated counterpart to /api/shop-chat for the admin's آزمایشگاه فروش
 * (sales playground): same streaming-proxy shape (tee the agent's SSE body,
 * relay one copy live, persist the finished reply from the other), but the
 * visitor is the signed-in shop owner's own sentinel EndUser
 * (PLAYGROUND_WEB_VISITOR_ID) instead of a slug/webVisitorId pair from the
 * request body, and `debug: true` is always sent so the agent's `done` event
 * carries the same path/state snapshot the old non-streaming playground
 * showed per turn.
 */
export async function POST(req: NextRequest) {
  const shop = await resolvePlaygroundShop()
  if (!shop) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const body = await req.json()
  const message = typeof body.message === "string" ? body.message.trim() : ""
  const mode = body.mode === "product" ? "product" : "explore"
  const productId = typeof body.productId === "string" ? body.productId : undefined

  if (!message) return NextResponse.json({ error: "پیام خالی است" }, { status: 400 })

  const endUser = await prisma.endUser.upsert({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId: PLAYGROUND_WEB_VISITOR_ID } },
    update: {},
    create: { shopId: shop.id, webVisitorId: PLAYGROUND_WEB_VISITOR_ID },
  })

  // A playground turn costs exactly what a customer's does, so it is counted
  // against the same quota; only the per-customer abuse limits are waived.
  const admission = await admitTurn({
    shopId: shop.id,
    endUserId: endUser.id,
    message,
    mode,
    productId,
    isOwner: true,
  })
  if (!admission.ok) {
    return sseTextResponse(OWNER_DENIAL_MESSAGES[admission.reason] ?? admission.message)
  }
  const conversation = admission.conversation
  // Same "<shopId>:<endUserId>:<conversationId>" shape the storefront uses -
  // "ریست حافظه دستیار" (which matches on "<shopId>:%") wipes this the same
  // way, and Langfuse's tracing groups turns by the same thread id either way.
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
        // No endUserId: the shop owner testing their own bot must never hit
        // the customer-facing weekly/monthly usage gate.
        mode: conversation.mode,
        productId: conversation.productId,
        threadId,
        message,
        debug: true,
      }),
    })
  } catch (err) {
    console.error("[playground] agent unreachable:", err)
    return NextResponse.json({ error: "سرویس دستیار در دسترس نیست" }, { status: 502 })
  }

  if (!agentRes.ok || !agentRes.body) {
    return NextResponse.json({ error: "سرویس دستیار در دسترس نیست" }, { status: 502 })
  }

  const [browserStream, persistStream] = agentRes.body.tee()

  // Fire-and-forget persistence, mirroring api/shop-chat/route.ts exactly.
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
      console.error("[playground] post-turn persistence failed:", err)
    }
  })()

  return new Response(browserStream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Conversation-Id": conversation.id,
    },
  })
}

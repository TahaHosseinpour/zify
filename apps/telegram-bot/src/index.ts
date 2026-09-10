import { Bot, InlineKeyboard } from "grammy"
import { prisma, type Prisma } from "@zify/db"
import type { ChatRequest, ChatResponse } from "@zify/shared"

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN!
const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:3001"

if (!BOT_TOKEN) throw new Error("TELEGRAM_BOT_TOKEN is required")

const bot = new Bot(BOT_TOKEN)

// ── Helpers ───────────────────────────────────────────────────────────────────

async function resolveShopFromSlug(slug: string) {
  return prisma.shop.findUnique({ where: { slug } })
}

async function upsertEndUser(shopId: string, telegramUserId: string, firstName?: string, username?: string) {
  return prisma.endUser.upsert({
    where: { shopId_telegramUserId: { shopId, telegramUserId } },
    update: { firstName: firstName ?? null, username: username ?? null },
    create: { shopId, telegramUserId, firstName: firstName ?? null, username: username ?? null },
  })
}

async function getOrCreateConversation(shopId: string, endUserId: string, mode: string, productId?: string) {
  const existing = await prisma.conversation.findFirst({
    where: { shopId, endUserId },
    orderBy: { startedAt: "desc" },
  })
  if (existing) return existing
  return prisma.conversation.create({
    data: { shopId, endUserId, mode, productId },
  })
}

async function callAgent(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${AGENT_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Agent error: ${res.status}`)
  return res.json() as Promise<ChatResponse>
}

// Matches the agent's own context budget, so a six-product answer is not
// silently cut to four cards.
const PRODUCT_CARD_LIMIT = 8

async function recordEvent(shopId: string, endUserId: string, type: string, metadata?: Record<string, unknown>) {
  await prisma.event.create({ data: { shopId, endUserId, type, metadata: metadata as Prisma.InputJsonValue | undefined } })
}

// ── /start handler ────────────────────────────────────────────────────────────

bot.command("start", async (ctx) => {
  const param = ctx.match ?? ""
  const from = ctx.from
  if (!from) return

  const telegramUserId = String(from.id)
  const firstName = from.first_name
  const username = from.username

  // Parse deep-link: slug or slug_productId
  let slug = ""
  let productId: string | undefined

  if (param) {
    const parts = param.split("_")
    slug = parts[0]
    if (parts.length > 1) productId = parts.slice(1).join("_")
  }

  if (!slug) {
    await ctx.reply(
      "سلام! 👋 لطفاً از طریق لینک اختصاصی فروشگاه وارد شوید.",
      { parse_mode: "HTML" }
    )
    return
  }

  const shop = await resolveShopFromSlug(slug)
  if (!shop) {
    await ctx.reply("فروشگاه یافت نشد.")
    return
  }

  const endUser = await upsertEndUser(shop.id, telegramUserId, firstName, username)
  const mode = productId ? "product" : "explore"
  await getOrCreateConversation(shop.id, endUser.id, mode, productId)
  await recordEvent(shop.id, endUser.id, "view")

  const welcomeMsg = productId
    ? `سلام ${firstName ?? ""}! 👋 به ${shop.name} خوش آمدید.\nبرای مشاهده اطلاعات این محصول آماده‌ام.`
    : `سلام ${firstName ?? ""}! 👋 به ${shop.name} خوش آمدید.\nمی‌توانم در یافتن محصول مناسب کمکتان کنم.`

  await ctx.reply(welcomeMsg)
})

// ── Message handler ───────────────────────────────────────────────────────────

bot.on("message:text", async (ctx) => {
  const from = ctx.from
  if (!from) return

  const telegramUserId = String(from.id)
  const userMessage = ctx.message.text

  // Find the most recent conversation for this user across all shops
  const endUser = await prisma.endUser.findFirst({
    where: { telegramUserId },
    orderBy: { createdAt: "desc" },
    include: { conversations: { orderBy: { startedAt: "desc" }, take: 1 } },
  })

  if (!endUser || endUser.conversations.length === 0) {
    await ctx.reply("لطفاً ابتدا از طریق لینک اختصاصی فروشگاه وارد شوید.")
    return
  }

  const conversation = endUser.conversations[0]

  // Record the user message
  await prisma.message.create({
    data: {
      conversationId: conversation.id,
      role: "user",
      content: userMessage,
    },
  })
  await recordEvent(endUser.shopId, endUser.id, "message")

  // Show typing indicator
  await ctx.replyWithChatAction("typing")

  try {
    const threadId = `${endUser.shopId}:${endUser.id}`

    const agentResponse = await callAgent({
      shopId: endUser.shopId,
      endUserId: endUser.id,
      mode: conversation.mode as "explore" | "product",
      productId: conversation.productId ?? undefined,
      threadId,
      message: userMessage,
    })

    // Record the assistant reply
    await prisma.message.create({
      data: {
        conversationId: conversation.id,
        role: "assistant",
        content: agentResponse.reply,
      },
    })
    await recordEvent(endUser.shopId, endUser.id, "message")

    // The agent decides whether this turn should push a purchase. A turn that
    // just told the customer to take their time must not sprout buy buttons.
    const showBuyActions = agentResponse.showBuyActions !== false

    // Send the assistant reply text (with a buy button if a purchase URL exists)
    if (showBuyActions && agentResponse.purchaseUrl) {
      const keyboard = new InlineKeyboard().url("🛒 خرید محصول", agentResponse.purchaseUrl)
      await ctx.reply(agentResponse.reply, { reply_markup: keyboard })
      // Rendering a link is not a click: Telegram url-buttons fire no callback,
      // so this records the impression. Recording it as "click" inflated the
      // dashboard's "کلیک‌های محصول" with every button that was merely shown.
      await recordEvent(endUser.shopId, endUser.id, "link_shown", {
        url: agentResponse.purchaseUrl,
      })
    } else {
      await ctx.reply(agentResponse.reply)
    }

    // Send a card per suggested product. Products without an image still get a
    // text card — skipping them silently dropped them from the conversation,
    // which broke comparisons of a list the agent had already described.
    const products = agentResponse.products ?? []
    for (const p of products.slice(0, PRODUCT_CARD_LIMIT)) {
      const priceText = p.price != null ? `\n💰 ${p.price.toLocaleString("fa-IR")} تومان` : ""
      const caption = `${p.name ?? ""}${priceText}`.trim()
      const keyboard =
        showBuyActions && p.productUrl
          ? new InlineKeyboard().url("🛒 مشاهده و خرید", p.productUrl)
          : undefined

      if (!p.imageUrl) {
        if (caption) await ctx.reply(caption, { reply_markup: keyboard })
        continue
      }
      try {
        await ctx.replyWithPhoto(p.imageUrl, {
          caption: caption || undefined,
          reply_markup: keyboard,
        })
      } catch (err) {
        // Telegram couldn't fetch/parse the image URL — fall back to text so the
        // product still appears.
        console.warn("[bot] failed to send product photo:", p.imageUrl, err)
        if (caption) await ctx.reply(caption, { reply_markup: keyboard })
      }
    }

    // If suggested products, record a search event
    if (agentResponse.suggestedProductIds && agentResponse.suggestedProductIds.length > 0) {
      await recordEvent(endUser.shopId, endUser.id, "search", {
        productIds: agentResponse.suggestedProductIds,
      })
    }

    // Carry the agent's own mode/product forward. These are sent back on the
    // next turn and overwrite the graph's state, so re-sending the mode stored
    // at /start undid every pin the agent made: the customer said "the second
    // one", the agent switched to product mode, and the next message reset it.
    const nextMode = agentResponse.mode ?? conversation.mode
    const nextProductId = agentResponse.productId ?? null
    if (nextMode !== conversation.mode || nextProductId !== conversation.productId) {
      await prisma.conversation.update({
        where: { id: conversation.id },
        data: { mode: nextMode, productId: nextProductId },
      })
    }
  } catch (err) {
    console.error("[bot] agent call failed:", err)
    await ctx.reply("متأسفانه در این لحظه مشکلی پیش آمده. لطفاً دوباره امتحان کنید.")
  }
})

// ── Error handler ─────────────────────────────────────────────────────────────

bot.catch((err) => {
  console.error("[bot] unhandled error:", err)
})

// ── Start ─────────────────────────────────────────────────────────────────────

console.log("[bot] starting long-polling...")
bot.start()

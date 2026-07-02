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

    // Send the assistant reply text (with a buy button if a purchase URL exists)
    if (agentResponse.purchaseUrl) {
      const keyboard = new InlineKeyboard().url("🛒 خرید محصول", agentResponse.purchaseUrl)
      await ctx.reply(agentResponse.reply, { reply_markup: keyboard })
      await recordEvent(endUser.shopId, endUser.id, "click", { url: agentResponse.purchaseUrl })
    } else {
      await ctx.reply(agentResponse.reply)
    }

    // Send product cards with images for the suggested products
    const products = agentResponse.products ?? []
    for (const p of products.slice(0, 4)) {
      if (!p.imageUrl) continue
      const priceText = p.price != null ? `\n💰 ${p.price.toLocaleString("fa-IR")} تومان` : ""
      const caption = `${p.name ?? ""}${priceText}`.trim()
      const keyboard = p.productUrl
        ? new InlineKeyboard().url("🛒 مشاهده و خرید", p.productUrl)
        : undefined
      try {
        await ctx.replyWithPhoto(p.imageUrl, {
          caption: caption || undefined,
          reply_markup: keyboard,
        })
      } catch (err) {
        // Telegram couldn't fetch/parse the image URL — skip this card silently
        console.warn("[bot] failed to send product photo:", p.imageUrl, err)
      }
    }

    // If suggested products, record a search event
    if (agentResponse.suggestedProductIds && agentResponse.suggestedProductIds.length > 0) {
      await recordEvent(endUser.shopId, endUser.id, "search", {
        productIds: agentResponse.suggestedProductIds,
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

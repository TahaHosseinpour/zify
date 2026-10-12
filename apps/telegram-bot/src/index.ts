import { Bot, InlineKeyboard } from "grammy"
import {
  prisma,
  type Prisma,
  getOrStartConversation,
  admitTurn,
  startNewConversation,
  resumeConversation,
  listRecentConversations,
  getUsageStatus,
  isChannelActive,
} from "@zify/db"
import type { ChatRequest, ChatResponse } from "@zify/shared"
import { formatDateTime, withNavRow } from "./ui"

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN!
const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:3001"
const AGENT_INTERNAL_KEY = process.env.AGENT_INTERNAL_KEY

if (!BOT_TOKEN) throw new Error("TELEGRAM_BOT_TOKEN is required")

const bot = new Bot(BOT_TOKEN)

// What a customer is told when the shop has switched its Telegram channel off
// in the panel (packages/db/src/channels.ts).
const TELEGRAM_OFF = "دستیار این فروشگاه در تلگرام فعال نیست."

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

// A telegram user can have /start'd more than one shop (a separate EndUser
// row each, @@unique([shopId, telegramUserId])) - a bare text message with no
// shop context picks whichever shop they most recently /start'd, same
// tie-break the code has always used.
async function resolveEndUserForTelegram(telegramUserId: string) {
  return prisma.endUser.findFirst({
    where: { telegramUserId },
    orderBy: { createdAt: "desc" },
  })
}

async function callAgent(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${AGENT_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // The agent only answers our own services (apps/agent/app/server.py).
      ...(AGENT_INTERNAL_KEY ? { "x-agent-key": AGENT_INTERNAL_KEY } : {}),
    },
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
  if (!(await isChannelActive(shop.id, "telegram"))) {
    await ctx.reply(TELEGRAM_OFF)
    return
  }

  const endUser = await upsertEndUser(shop.id, telegramUserId, firstName, username)
  // A link to a product that is gone, or that belongs to another shop, opens
  // the shop's general chat instead of pinning an id the agent cannot load.
  const product = productId
    ? await prisma.product.findFirst({ where: { id: productId, shopId: shop.id, isActive: true } })
    : null
  const mode = product ? "product" : "explore"
  await getOrStartConversation(shop.id, endUser.id, mode, product?.id)
  await recordEvent(shop.id, endUser.id, "view")

  // The shop's own greeting (panel settings) replaces the built-in one; a
  // product link still names the product either way.
  const greeting =
    shop.welcomeMessage?.trim() ||
    `سلام ${firstName ?? ""}! 👋 به ${shop.name} خوش آمدید.` +
      (product ? "" : "\nمی‌توانم در یافتن محصول مناسب کمکتان کنم.")
  const welcomeMsg = product
    ? `${greeting}\nدرباره «${product.name}» هر سؤالی دارید بپرسید.`
    : greeting

  await ctx.reply(welcomeMsg, { reply_markup: withNavRow() })
})

// ── Message handler ───────────────────────────────────────────────────────────

bot.on("message:text", async (ctx) => {
  const from = ctx.from
  if (!from) return

  const telegramUserId = String(from.id)
  const userMessage = ctx.message.text

  const endUser = await resolveEndUserForTelegram(telegramUserId)
  if (!endUser) {
    await ctx.reply("لطفاً ابتدا از طریق لینک اختصاصی فروشگاه وارد شوید.")
    return
  }
  if (!(await isChannelActive(endUser.shopId, "telegram"))) {
    await ctx.reply(TELEGRAM_OFF)
    return
  }

  // The gate every channel shares (packages/db/src/billing.ts): is this
  // shop's subscription live, is there quota left, is this customer within
  // their limits. It also picks the conversation - the active one within 24h
  // while it has room, otherwise a fresh one (fresh LangGraph memory too).
  const admission = await admitTurn({
    shopId: endUser.shopId,
    endUserId: endUser.id,
    message: userMessage,
    mode: "explore",
  })
  if (!admission.ok) {
    await ctx.reply(admission.message)
    return
  }
  const conversation = admission.conversation

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
    const threadId = `${endUser.shopId}:${endUser.id}:${conversation.id}`

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

    // Send the assistant reply text (with a buy button if a purchase URL exists),
    // plus the persistent nav row (new chat / history / usage) on this main reply.
    if (showBuyActions && agentResponse.purchaseUrl) {
      const keyboard = withNavRow(new InlineKeyboard().url("🛒 خرید محصول", agentResponse.purchaseUrl))
      await ctx.reply(agentResponse.reply, { reply_markup: keyboard })
      // Rendering a link is not a click: Telegram url-buttons fire no callback,
      // so this records the impression. Recording it as "click" inflated the
      // dashboard's "کلیک‌های محصول" with every button that was merely shown.
      await recordEvent(endUser.shopId, endUser.id, "link_shown", {
        url: agentResponse.purchaseUrl,
      })
    } else {
      await ctx.reply(agentResponse.reply, { reply_markup: withNavRow() })
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

// ── Nav buttons: new chat / history / resume / usage ─────────────────────────

bot.on("callback_query:data", async (ctx) => {
  const from = ctx.from
  const data = ctx.callbackQuery.data
  if (!from) return

  const telegramUserId = String(from.id)
  const endUser = await resolveEndUserForTelegram(telegramUserId)
  if (!endUser) {
    await ctx.answerCallbackQuery({ text: "لطفاً ابتدا از طریق لینک فروشگاه وارد شوید." })
    return
  }

  if (data === "newchat") {
    await startNewConversation(endUser.shopId, endUser.id)
    await ctx.answerCallbackQuery({ text: "چت جدید شروع شد ✅" })
    await ctx.reply("چت جدید شروع شد. چطور می‌تونم کمکتون کنم؟", { reply_markup: withNavRow() })
    return
  }

  if (data === "history") {
    const conversations = await listRecentConversations(endUser.shopId, endUser.id, 10)
    if (conversations.length === 0) {
      await ctx.answerCallbackQuery({ text: "هنوز چت قبلی‌ای ندارید." })
      return
    }
    const keyboard = new InlineKeyboard()
    for (const c of conversations) {
      keyboard.text(formatDateTime(c.lastMessageAt), `resume:${c.id}`).row()
    }
    await ctx.answerCallbackQuery()
    await ctx.reply("کدوم گفت‌وگو رو می‌خواید ادامه بدید؟", { reply_markup: keyboard })
    return
  }

  if (data.startsWith("resume:")) {
    const conversationId = data.slice("resume:".length)
    const resumed = await resumeConversation(endUser.shopId, endUser.id, conversationId)
    if (!resumed) {
      await ctx.answerCallbackQuery({ text: "این گفتگو پیدا نشد." })
      return
    }
    await ctx.answerCallbackQuery({ text: "این گفتگو ادامه پیدا می‌کنه ✅" })
    await ctx.reply("این گفتگو رو ادامه می‌دیم. بفرمایید 🙂", { reply_markup: withNavRow() })
    return
  }

  if (data === "usage") {
    const status = await getUsageStatus(endUser.id)
    await ctx.answerCallbackQuery()
    const weeklyPct = Math.min(100, Math.round((status.weeklyUsed / status.weeklyLimit) * 100))
    const monthlyPct = Math.min(100, Math.round((status.monthlyUsed / status.monthlyLimit) * 100))
    await ctx.reply(
      "📊 سقف مصرف شما:\n\n" +
        `هفتگی: ${weeklyPct}٪ (${status.weeklyUsed.toLocaleString("fa-IR")} از ${status.weeklyLimit.toLocaleString("fa-IR")} توکن)\n` +
        `بازنشانی: ${status.weeklyResetAt.toLocaleDateString("fa-IR")}\n\n` +
        `ماهانه: ${monthlyPct}٪ (${status.monthlyUsed.toLocaleString("fa-IR")} از ${status.monthlyLimit.toLocaleString("fa-IR")} توکن)\n` +
        `بازنشانی: ${status.monthlyResetAt.toLocaleDateString("fa-IR")}`
    )
    return
  }

  await ctx.answerCallbackQuery()
})

// ── Error handler ─────────────────────────────────────────────────────────────

bot.catch((err) => {
  console.error("[bot] unhandled error:", err)
})

// ── Start ─────────────────────────────────────────────────────────────────────

console.log("[bot] starting long-polling...")
bot.start()

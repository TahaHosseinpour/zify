import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import {
  CUSTOM_PLAN_KEY,
  clampCustomConversations,
  customPlanPrice,
  isPlanDuration,
  planPrice,
} from "@zify/shared"
import { checkRateLimit, clientIp } from "@/lib/rate-limit"
import { toEnglishDigits } from "@/lib/utils"
import { DURATION_LABELS, formatToman } from "@/lib/leads"

const WINDOW_MS = 60 * 60 * 1000
const MAX_PER_WINDOW = 5

function text(value: unknown, max: number): string {
  return typeof value === "string" ? value.trim().slice(0, max) : ""
}

/** Tell the platform's operators a request came in, if a chat is configured
 * for it. Best effort: the request is already saved either way. */
async function notifyOperators(summary: string) {
  const token = process.env.TELEGRAM_BOT_TOKEN
  const chatId = process.env.PLATFORM_ADMIN_TELEGRAM_CHAT_ID
  if (!token || !chatId) return
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: summary }),
    })
  } catch (err) {
    console.error("[leads] operator notification failed:", err)
  }
}

/**
 * Public: the pricing page's "request this plan" form. Nothing is charged and
 * nothing is activated here - it only records who wants what, so we can call
 * them. The price is recomputed on the server from the plan itself; the number
 * the browser showed is never trusted.
 */
export async function POST(req: NextRequest) {
  if (!checkRateLimit(`lead:${clientIp(req)}`, MAX_PER_WINDOW, WINDOW_MS).allowed) {
    return NextResponse.json(
      { error: "تعداد درخواست‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  const body = await req.json()
  const fullName = text(body.fullName, 100)
  const mobile = toEnglishDigits(text(body.mobile, 20)).replace(/[\s-]/g, "")
  const shopName = text(body.shopName, 100)
  const shopUrl = text(body.shopUrl, 200)
  const message = text(body.message, 1000)
  const planKey = text(body.planKey, 40)
  const months = Number(body.months)

  if (!fullName || !shopName) {
    return NextResponse.json({ error: "نام و نام فروشگاه الزامی است." }, { status: 400 })
  }
  if (!/^09\d{9}$/.test(mobile)) {
    return NextResponse.json({ error: "شماره موبایل معتبر نیست." }, { status: 400 })
  }
  if (!isPlanDuration(months)) {
    return NextResponse.json({ error: "مدت اشتراک نامعتبر است." }, { status: 400 })
  }

  let conversationsPerMonth: number
  let quotedPriceToman: number
  let planName: string
  if (planKey === CUSTOM_PLAN_KEY) {
    conversationsPerMonth = clampCustomConversations(Number(body.conversationsPerMonth) || 0)
    quotedPriceToman = customPlanPrice(conversationsPerMonth, months)
    planName = "سفارشی"
  } else {
    const plan = await prisma.plan.findFirst({ where: { key: planKey, isActive: true } })
    if (!plan) return NextResponse.json({ error: "پلن یافت نشد." }, { status: 400 })
    conversationsPerMonth = plan.conversationsPerMonth
    quotedPriceToman = planPrice(plan, months)
    planName = plan.name
  }

  await prisma.lead.create({
    data: {
      fullName,
      mobile,
      shopName,
      shopUrl: shopUrl || null,
      planKey,
      months,
      conversationsPerMonth,
      quotedPriceToman,
      message: message || null,
    },
  })

  await notifyOperators(
    `درخواست خرید جدید\n` +
      `${fullName} - ${mobile}\n` +
      `فروشگاه: ${shopName}${shopUrl ? ` (${shopUrl})` : ""}\n` +
      `پلن: ${planName}، ${DURATION_LABELS[months]}، ${conversationsPerMonth.toLocaleString("fa-IR")} گفتگو در ماه\n` +
      `مبلغ: ${formatToman(quotedPriceToman)}`,
  )

  return NextResponse.json({ ok: true })
}

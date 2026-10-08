import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma, getQuotaStatus } from "@zify/db"

// Telegram's global send cap is ~30 msg/sec across all chats. We send in
// small concurrent batches with a pause between them to stay well under
// that without making a large user list take forever - there's no queue/
// background-job infra in this repo yet, so this has to finish inside one
// request (see apps/admin/app/dashboard/products/page.tsx importRows for
// the same "loop it in the route handler" precedent).
const BATCH_SIZE = 20
const BATCH_DELAY_MS = 1000

// Large recipient lists can take minutes; raise the route's execution
// budget past Next.js/Vercel's default (a no-op on platforms that don't
// read this export).
export const maxDuration = 300

export async function POST(req: Request) {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 })

  const { message } = await req.json()
  if (typeof message !== "string" || !message.trim()) {
    return NextResponse.json({ error: "پیام نمی‌تواند خالی باشد" }, { status: 400 })
  }

  const token = process.env.TELEGRAM_BOT_TOKEN
  if (!token) {
    return NextResponse.json({ error: "ربات تلگرام پیکربندی نشده" }, { status: 500 })
  }

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json({ error: "فروشگاهی یافت نشد" }, { status: 404 })

  // Broadcasts are a subscription feature with a per-period allowance: one
  // click messages every customer the shop has, so it is neither free to
  // offer nor safe to leave uncounted. Each send is recorded as an event,
  // which is what the next check counts.
  const quota = await getQuotaStatus(shop.id)
  if (!quota.subscription || !quota.periodStart) {
    return NextResponse.json(
      { error: "ارسال پیام همگانی فقط با اشتراک فعال ممکن است." },
      { status: 403 },
    )
  }
  const sentThisPeriod = await prisma.event.count({
    where: { shopId: shop.id, type: "broadcast", createdAt: { gte: quota.periodStart } },
  })
  const allowed = quota.subscription.maxBroadcastsPerMonth
  if (sentThisPeriod >= allowed) {
    return NextResponse.json(
      { error: `سقف ${allowed.toLocaleString("fa-IR")} پیام همگانی این دوره پر شده است.` },
      { status: 429 },
    )
  }
  await prisma.event.create({ data: { shopId: shop.id, type: "broadcast" } })

  const recipients = await prisma.endUser.findMany({
    where: { shopId: shop.id, telegramUserId: { not: null } },
    select: { telegramUserId: true },
  })

  let sent = 0
  let failed = 0

  for (let i = 0; i < recipients.length; i += BATCH_SIZE) {
    const batch = recipients.slice(i, i + BATCH_SIZE)
    const results = await Promise.all(
      batch.map((r) =>
        fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: r.telegramUserId, text: message }),
        })
          .then((res) => res.ok)
          .catch(() => false)
      )
    )
    sent += results.filter(Boolean).length
    failed += results.filter((ok) => !ok).length
    if (i + BATCH_SIZE < recipients.length) {
      await new Promise((resolve) => setTimeout(resolve, BATCH_DELAY_MS))
    }
  }

  return NextResponse.json({ sent, failed, total: recipients.length })
}

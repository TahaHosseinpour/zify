import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"
import { reembedAllForShop } from "@/lib/embeddings"
import { AGENT_URL, agentHeaders } from "@/lib/agent"
import { checkRateLimit } from "@/lib/rate-limit"

// Every run re-embeds the shop's whole catalog, which is paid for per call.
const REINDEX_WINDOW_MS = 60 * 60 * 1000
const REINDEX_MAX_PER_WINDOW = 3

async function getShop(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

export async function POST() {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const shop = await getShop(session.userId)
  if (!shop) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  if (!checkRateLimit(`reindex:${shop.id}`, REINDEX_MAX_PER_WINDOW, REINDEX_WINDOW_MS).allowed) {
    return NextResponse.json(
      { error: "بازسازی ایندکس بیش از حد تکرار شده است. یک ساعت بعد دوباره تلاش کنید." },
      { status: 429 },
    )
  }

  // 1) Re-index embeddings for the latest products / FAQs / shop info.
  let reindexed: { products: number; faqs: number } | null = null
  try {
    reindexed = await reembedAllForShop(shop.id)
  } catch (err) {
    console.error("[admin] reindex failed:", err)
    return NextResponse.json({ error: "خطا در بازسازی ایندکس" }, { status: 500 })
  }

  // 2) Clear the agent's persisted conversation memory for this shop.
  try {
    const res = await fetch(`${AGENT_URL}/admin/reset-memory`, {
      method: "POST",
      headers: agentHeaders(),
      body: JSON.stringify({ shopId: shop.id }),
    })
    if (!res.ok) throw new Error(`agent responded ${res.status}`)
  } catch (err) {
    // Embeddings are already refreshed; report memory-clear failure but don't
    // pretend the whole thing failed.
    console.error("[admin] reset-memory failed:", err)
    return NextResponse.json(
      { ok: true, reindexed, memoryCleared: false, warning: "ایندکس بازسازی شد اما حافظه گفتگوها پاک نشد (سرویس ایجنت در دسترس نبود)" },
      { status: 200 },
    )
  }

  return NextResponse.json({ ok: true, reindexed, memoryCleared: true })
}

import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { getAdmin } from "@/lib/admin-auth"

/**
 * Platform settings (platform admins only). Currently one: the dollar rate
 * every model cost is converted to toman with (apps/agent/app/metering.py
 * re-reads it every few minutes).
 */
export async function PATCH(req: NextRequest) {
  const admin = await getAdmin()
  if (!admin) return NextResponse.json({ error: "دسترسی ندارید" }, { status: 403 })

  const body = await req.json()
  const usdToman = Math.floor(Number(body.usdToman))
  if (!Number.isFinite(usdToman) || usdToman < 1_000 || usdToman > 100_000_000) {
    return NextResponse.json({ error: "نرخ دلار نامعتبر است." }, { status: 400 })
  }

  await prisma.setting.upsert({
    where: { key: "usd_toman" },
    update: { value: String(usdToman) },
    create: { key: "usd_toman", value: String(usdToman) },
  })
  return NextResponse.json({ ok: true })
}

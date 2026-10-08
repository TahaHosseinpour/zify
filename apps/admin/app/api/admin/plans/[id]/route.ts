import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { getAdmin } from "@/lib/admin-auth"
import { maxMonthlyCostToman } from "@zify/shared"

const INT_FIELDS = [
  "conversationsPerMonth",
  "monthlyPriceToman",
  "discountPercent3Months",
  "discountPercent12Months",
  "maxActiveProducts",
  "maxMonthlyProductUploads",
  "maxFaqItems",
  "maxBroadcastsPerMonth",
] as const

/**
 * Edit a plan (platform admins only). Affects future activations only: every
 * subscription carries its own copy of the terms it was sold on.
 */
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const admin = await getAdmin()
  if (!admin) return NextResponse.json({ error: "دسترسی ندارید" }, { status: 403 })

  const { id } = await params
  const plan = await prisma.plan.findUnique({ where: { id } })
  if (!plan) return NextResponse.json({ error: "پلن یافت نشد." }, { status: 404 })

  const body = await req.json()
  const data: Record<string, number | string | boolean | null> = {}

  for (const field of INT_FIELDS) {
    if (body[field] === undefined) continue
    const value = Math.floor(Number(body[field]))
    if (!Number.isFinite(value) || value < 0) {
      return NextResponse.json({ error: `مقدار «${field}» نامعتبر است.` }, { status: 400 })
    }
    data[field] = value
  }
  if (typeof body.name === "string" && body.name.trim()) data.name = body.name.trim().slice(0, 80)
  if (typeof body.description === "string") data.description = body.description.trim().slice(0, 300) || null
  if (typeof body.isActive === "boolean") data.isActive = body.isActive

  // The one rule a plan can never break: its cheapest price must still cover
  // the most its conversations can cost. Checked on the terms as they would
  // be after this edit, for the most heavily discounted duration.
  const next = { ...plan, ...data } as typeof plan
  for (const discount of [next.discountPercent3Months, next.discountPercent12Months]) {
    if (discount > 100) {
      return NextResponse.json({ error: "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد." }, { status: 400 })
    }
  }
  const worstDiscount = Math.max(next.discountPercent3Months, next.discountPercent12Months)
  const cheapestMonthlyPrice = (next.monthlyPriceToman * (100 - worstDiscount)) / 100
  const costCeiling = maxMonthlyCostToman(next.conversationsPerMonth)
  if (cheapestMonthlyPrice < costCeiling) {
    return NextResponse.json(
      {
        error:
          `با این اعداد، قیمت ماهانه پس از تخفیف (${Math.round(cheapestMonthlyPrice).toLocaleString("fa-IR")} تومان) ` +
          `از حداکثر هزینه‌ی این تعداد گفتگو (${costCeiling.toLocaleString("fa-IR")} تومان) کمتر می‌شود.`,
      },
      { status: 400 },
    )
  }

  await prisma.plan.update({ where: { id }, data })
  return NextResponse.json({ ok: true })
}

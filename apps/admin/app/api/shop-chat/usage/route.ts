import { NextRequest, NextResponse } from "next/server"
import { getUsageStatus, WEEKLY_INPUT_TOKEN_LIMIT, MONTHLY_INPUT_TOKEN_LIMIT } from "@zify/db"
import { resolveShopVisitor } from "@/lib/resolve-shop-visitor"
import { readVisitorId } from "@/lib/visitor-cookie"

export async function GET(req: NextRequest) {
  const slug = req.nextUrl.searchParams.get("slug") ?? ""
  if (!slug) return NextResponse.json({ error: "slug الزامی است" }, { status: 400 })
  // No signed cookie yet means no identity yet: resolves to "never chatted".
  const webVisitorId = readVisitorId(req) ?? ""

  const resolved = await resolveShopVisitor(slug, webVisitorId)
  if (!resolved) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  // A visitor who has never chatted yet has used nothing - no EndUser row to
  // read from, and none needs to be created just to answer this.
  if (!resolved.endUser) {
    return NextResponse.json({
      weeklyUsed: 0,
      weeklyLimit: WEEKLY_INPUT_TOKEN_LIMIT,
      weeklyResetAt: null,
      monthlyUsed: 0,
      monthlyLimit: MONTHLY_INPUT_TOKEN_LIMIT,
      monthlyResetAt: null,
    })
  }

  const status = await getUsageStatus(resolved.endUser.id)
  return NextResponse.json(status)
}

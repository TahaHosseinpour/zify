import { NextRequest, NextResponse } from "next/server"
import { getUsageStatus } from "@zify/db"
import { resolveShopVisitor } from "@/lib/resolve-shop-visitor"

export async function GET(req: NextRequest) {
  const slug = req.nextUrl.searchParams.get("slug") ?? ""
  const webVisitorId = req.nextUrl.searchParams.get("webVisitorId") ?? ""
  if (!slug || !webVisitorId) {
    return NextResponse.json({ error: "slug و webVisitorId الزامی است" }, { status: 400 })
  }

  const resolved = await resolveShopVisitor(slug, webVisitorId)
  if (!resolved) return NextResponse.json({ error: "فروشگاه یافت نشد" }, { status: 404 })

  // A visitor who has never chatted yet has used nothing - no EndUser row to
  // read from, and none needs to be created just to answer this.
  if (!resolved.endUser) {
    return NextResponse.json({
      weeklyUsed: 0,
      weeklyLimit: 20_000,
      weeklyResetAt: null,
      monthlyUsed: 0,
      monthlyLimit: 40_000,
      monthlyResetAt: null,
    })
  }

  const status = await getUsageStatus(resolved.endUser.id)
  return NextResponse.json(status)
}

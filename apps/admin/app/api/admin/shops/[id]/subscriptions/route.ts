import { NextRequest, NextResponse } from "next/server"
import { getAdmin } from "@/lib/admin-auth"
import { activateSubscription } from "@/lib/subscriptions"

/** Activate a plan for a shop (platform admins only). */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const admin = await getAdmin()
  if (!admin) return NextResponse.json({ error: "دسترسی ندارید" }, { status: 403 })

  const { id } = await params
  const body = await req.json()

  const result = await activateSubscription({
    shopId: id,
    planKey: typeof body.planKey === "string" ? body.planKey : "",
    months: Number(body.months),
    conversationsPerMonth: Number(body.conversationsPerMonth),
    note: typeof body.note === "string" ? body.note : undefined,
    adminId: admin.id,
  })
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ ok: true, subscriptionId: result.subscription.id })
}

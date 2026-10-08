import { NextResponse } from "next/server"
import { prisma, getQuotaStatus } from "@zify/db"
import { getSession } from "@/lib/auth"

/** Where the signed-in owner's shop stands: its plan, when it ends, and how
 * many of this period's conversations are used. */
export async function GET() {
  const session = await getSession()
  if (!session) return NextResponse.json({ error: "احراز هویت لازم است" }, { status: 401 })

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  const shop = user?.shops[0]
  if (!shop) return NextResponse.json({ active: false })

  const quota = await getQuotaStatus(shop.id)
  if (!quota.subscription) return NextResponse.json({ active: false })

  return NextResponse.json({
    active: true,
    planName: quota.subscription.planName,
    endsAt: quota.subscription.endsAt,
    daysLeft: Math.max(
      0,
      Math.ceil((quota.subscription.endsAt.getTime() - Date.now()) / (24 * 60 * 60 * 1000)),
    ),
    periodEnd: quota.periodEnd,
    conversationsUsed: quota.conversationsUsed,
    conversationsLimit: quota.conversationsLimit,
  })
}

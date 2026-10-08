import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { getAdmin } from "@/lib/admin-auth"

/** Cancel a subscription (platform admins only). The assistant stops on the
 * shop's next message; nothing is deleted, the row stays as the record. */
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const admin = await getAdmin()
  if (!admin) return NextResponse.json({ error: "دسترسی ندارید" }, { status: 403 })

  const { id } = await params
  const body = await req.json()
  if (body.status !== "cancelled") {
    return NextResponse.json({ error: "تنها تغییر مجاز، لغو اشتراک است." }, { status: 400 })
  }

  const result = await prisma.subscription.updateMany({
    where: { id, status: "active" },
    data: { status: "cancelled" },
  })
  if (result.count === 0) {
    return NextResponse.json({ error: "اشتراک فعالی با این شناسه یافت نشد." }, { status: 404 })
  }
  return NextResponse.json({ ok: true })
}

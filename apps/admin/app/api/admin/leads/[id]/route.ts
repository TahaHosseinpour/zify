import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@zify/db"
import { getAdmin } from "@/lib/admin-auth"
import { LEAD_STATUSES } from "@/lib/leads"

/** Move a pricing-page request along (platform admins only). */
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const admin = await getAdmin()
  if (!admin) return NextResponse.json({ error: "دسترسی ندارید" }, { status: 403 })

  const { id } = await params
  const body = await req.json()

  const data: { status?: string; adminNote?: string | null } = {}
  if (body.status !== undefined) {
    if (!(body.status in LEAD_STATUSES)) {
      return NextResponse.json({ error: "وضعیت نامعتبر است." }, { status: 400 })
    }
    data.status = body.status
  }
  if (body.adminNote !== undefined) {
    data.adminNote = typeof body.adminNote === "string" ? body.adminNote.trim().slice(0, 2000) || null : null
  }

  const result = await prisma.lead.updateMany({ where: { id }, data })
  if (result.count === 0) return NextResponse.json({ error: "درخواست یافت نشد." }, { status: 404 })
  return NextResponse.json({ ok: true })
}

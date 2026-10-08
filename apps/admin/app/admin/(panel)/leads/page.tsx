import { prisma } from "@zify/db"
import { Card, CardContent } from "@/components/ui/card"
import { DURATION_LABELS, formatDate, formatToman } from "@/lib/leads"
import { toPersianDigits } from "@/lib/utils"
import { LeadControls } from "./lead-controls"

export default async function AdminLeadsPage() {
  const [leads, plans] = await Promise.all([
    prisma.lead.findMany({ orderBy: { createdAt: "desc" }, take: 200 }),
    prisma.plan.findMany({ select: { key: true, name: true } }),
  ])
  const planNames = new Map(plans.map((p) => [p.key, p.name]))
  const newCount = leads.filter((l) => l.status === "new").length

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {leads.length.toLocaleString("fa-IR")} درخواست، {newCount.toLocaleString("fa-IR")} بررسی‌نشده
      </p>

      {leads.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          هنوز درخواستی از صفحه‌ی قیمت‌ها ثبت نشده است
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {leads.map((lead) => (
            <Card key={lead.id}>
              <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex min-w-0 flex-col gap-1 text-sm">
                  <p className="font-semibold">
                    {lead.shopName}
                    <span className="font-normal text-muted-foreground">، {lead.fullName}</span>
                  </p>
                  <p className="text-muted-foreground">
                    <a href={`tel:${lead.mobile}`} className="hover:text-primary">
                      {toPersianDigits(lead.mobile)}
                    </a>
                    {lead.shopUrl && (
                      <>
                        {" · "}
                        <span dir="ltr">{lead.shopUrl}</span>
                      </>
                    )}
                  </p>
                  <p>
                    {planNames.get(lead.planKey) ?? "سفارشی"}، {DURATION_LABELS[lead.months] ?? `${lead.months} ماه`}،{" "}
                    {lead.conversationsPerMonth.toLocaleString("fa-IR")} گفتگو در ماه، {formatToman(lead.quotedPriceToman)}
                  </p>
                  {lead.message && <p className="whitespace-pre-wrap text-muted-foreground">{lead.message}</p>}
                  <p className="text-xs text-muted-foreground">{formatDate(lead.createdAt)}</p>
                </div>
                <LeadControls id={lead.id} status={lead.status} adminNote={lead.adminNote ?? ""} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

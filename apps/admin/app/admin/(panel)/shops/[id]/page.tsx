import Link from "next/link"
import { notFound } from "next/navigation"
import { prisma, getQuotaStatus, MAX_CONVERSATION_COST_TOMAN } from "@zify/db"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { DURATION_LABELS, formatDate, formatToman } from "@/lib/leads"
import { toPersianDigits } from "@/lib/utils"
import { ActivateForm } from "./activate-form"
import { CancelSubscriptionButton } from "./cancel-button"

export default async function AdminShopPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const shop = await prisma.shop.findUnique({
    where: { id },
    include: {
      owner: { select: { mobile: true, fullName: true } },
      subscriptions: { orderBy: { createdAt: "desc" } },
    },
  })
  if (!shop) notFound()

  const [quota, plans, productCount] = await Promise.all([
    getQuotaStatus(shop.id),
    prisma.plan.findMany({ where: { isActive: true }, orderBy: { sortOrder: "asc" } }),
    prisma.product.count({ where: { shopId: shop.id, isActive: true } }),
  ])
  const active = quota.subscription
  const now = new Date()

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link href="/admin" className="text-xs text-muted-foreground hover:text-primary">
          بازگشت به فهرست فروشگاه‌ها
        </Link>
        <h2 className="mt-1 text-lg font-bold">{shop.name}</h2>
        <p className="text-sm text-muted-foreground">
          {shop.owner.fullName ?? "بدون نام"}، {toPersianDigits(shop.owner.mobile)}، {productCount.toLocaleString("fa-IR")} محصول فعال
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">وضعیت فعلی</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {active ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">پلن</span>
                  <Badge variant="secondary">
                    {active.planName}، {DURATION_LABELS[active.months] ?? `${active.months} ماه`}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">پایان اشتراک</span>
                  <span>{formatDate(active.endsAt)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">گفتگوی این دوره</span>
                  <span>
                    {quota.conversationsUsed.toLocaleString("fa-IR")} از{" "}
                    {quota.conversationsLimit.toLocaleString("fa-IR")}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">هزینه‌ی واقعی این دوره</span>
                  <span>{formatToman(quota.costToman)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">سقف هزینه‌ی این دوره</span>
                  <span>{formatToman(quota.conversationsLimit * MAX_CONVERSATION_COST_TOMAN)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">مبلغ دریافتی</span>
                  <span>{formatToman(active.priceToman)}</span>
                </div>
                <CancelSubscriptionButton subscriptionId={active.id} />
              </>
            ) : (
              <p className="text-muted-foreground">
                این فروشگاه اشتراک فعالی ندارد و دستیارش خاموش است.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{active ? "تغییر یا تمدید پلن" : "فعال‌سازی پلن"}</CardTitle>
          </CardHeader>
          <CardContent>
            <ActivateForm
              shopId={shop.id}
              hasActive={Boolean(active)}
              plans={plans.map((p) => ({
                key: p.key,
                name: p.name,
                conversationsPerMonth: p.conversationsPerMonth,
                monthlyPriceToman: p.monthlyPriceToman,
                discountPercent3Months: p.discountPercent3Months,
                discountPercent12Months: p.discountPercent12Months,
              }))}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">تاریخچه‌ی اشتراک‌ها</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {shop.subscriptions.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">هنوز اشتراکی فعال نشده است</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">پلن</TableHead>
                  <TableHead className="text-right">از</TableHead>
                  <TableHead className="text-right">تا</TableHead>
                  <TableHead className="text-right">گفتگو در ماه</TableHead>
                  <TableHead className="text-right">مبلغ</TableHead>
                  <TableHead className="text-right">وضعیت</TableHead>
                  <TableHead className="text-right">یادداشت</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shop.subscriptions.map((s) => {
                  const state =
                    s.status === "cancelled" ? "لغوشده" : s.endsAt <= now ? "پایان‌یافته" : "فعال"
                  return (
                    <TableRow key={s.id}>
                      <TableCell>
                        {s.planName}، {DURATION_LABELS[s.months] ?? `${s.months} ماه`}
                      </TableCell>
                      <TableCell>{formatDate(s.startsAt)}</TableCell>
                      <TableCell>{formatDate(s.endsAt)}</TableCell>
                      <TableCell>{s.conversationsPerMonth.toLocaleString("fa-IR")}</TableCell>
                      <TableCell>{formatToman(s.priceToman)}</TableCell>
                      <TableCell>
                        <Badge variant={state === "فعال" ? "default" : "outline"}>{state}</Badge>
                      </TableCell>
                      <TableCell className="max-w-56 truncate text-muted-foreground">{s.note ?? "—"}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

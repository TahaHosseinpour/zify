import Link from "next/link"
import { prisma, quotaPeriodStart } from "@zify/db"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDate, formatToman } from "@/lib/leads"
import { toPersianDigits } from "@/lib/utils"

const DAY_MS = 24 * 60 * 60 * 1000

async function loadShops() {
  const now = new Date()
  const shops = await prisma.shop.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      owner: { select: { mobile: true, fullName: true } },
      subscriptions: {
        where: { status: "active", startsAt: { lte: now }, endsAt: { gt: now } },
        orderBy: { endsAt: "desc" },
        take: 1,
      },
    },
  })

  return Promise.all(
    shops.map(async (shop) => {
      const subscription = shop.subscriptions[0] ?? null
      if (!subscription) return { shop, subscription, used: 0, costToman: 0, daysLeft: 0 }

      const usage = await prisma.conversation.aggregate({
        where: { shopId: shop.id, billedAt: { gte: quotaPeriodStart(subscription, now) } },
        _count: { _all: true },
        _sum: { costToman: true },
      })
      return {
        shop,
        subscription,
        used: usage._count._all,
        costToman: Number(usage._sum.costToman ?? 0),
        daysLeft: Math.max(0, Math.ceil((subscription.endsAt.getTime() - now.getTime()) / DAY_MS)),
      }
    }),
  )
}

export default async function AdminShopsPage() {
  const rows = await loadShops()
  const activeCount = rows.filter((r) => r.subscription).length

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {rows.length.toLocaleString("fa-IR")} فروشگاه، {activeCount.toLocaleString("fa-IR")} با اشتراک فعال
      </p>

      <Card>
        <CardContent className="p-0">
          {rows.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">هنوز فروشگاهی ثبت نشده است</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">فروشگاه</TableHead>
                  <TableHead className="text-right">مالک</TableHead>
                  <TableHead className="text-right">پلن</TableHead>
                  <TableHead className="text-right">پایان اشتراک</TableHead>
                  <TableHead className="text-right">گفتگوی این دوره</TableHead>
                  <TableHead className="text-right">هزینه‌ی واقعی دوره</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(({ shop, subscription, used, costToman, daysLeft }) => {
                  return (
                    <TableRow key={shop.id}>
                      <TableCell>
                        <Link href={`/admin/shops/${shop.id}`} className="font-medium text-primary hover:underline">
                          {shop.name}
                        </Link>
                        <div className="text-xs text-muted-foreground" dir="ltr">
                          {shop.slug}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">{shop.owner.fullName ?? "—"}</div>
                        <div className="text-xs text-muted-foreground">{toPersianDigits(shop.owner.mobile)}</div>
                      </TableCell>
                      <TableCell>
                        {subscription ? (
                          <Badge variant="secondary">{subscription.planName}</Badge>
                        ) : (
                          <Badge variant="outline">بدون اشتراک</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {subscription ? (
                          <>
                            {formatDate(subscription.endsAt)}
                            <div className="text-xs text-muted-foreground">
                              {daysLeft.toLocaleString("fa-IR")} روز مانده
                            </div>
                          </>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {subscription
                          ? `${used.toLocaleString("fa-IR")} از ${subscription.conversationsPerMonth.toLocaleString("fa-IR")}`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-sm">{subscription ? formatToman(costToman) : "—"}</TableCell>
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

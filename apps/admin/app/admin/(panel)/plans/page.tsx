import { prisma } from "@zify/db"
import { CONVERSATION_COST_CAP_TOMAN, CUSTOM_PRICE_PER_CONVERSATION_TOMAN } from "@zify/shared"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatToman } from "@/lib/leads"
import { PlanEditor } from "./plan-editor"
import { UsdRateEditor } from "./usd-rate-editor"

export default async function AdminPlansPage() {
  const [plans, rate] = await Promise.all([
    prisma.plan.findMany({ orderBy: { sortOrder: "asc" } }),
    prisma.setting.findUnique({ where: { key: "usd_toman" } }),
  ])

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">مبنای قیمت‌گذاری</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          <p className="leading-relaxed text-muted-foreground">
            هر گفتگو حداکثر {formatToman(CONVERSATION_COST_CAP_TOMAN)} هزینه‌ی مدل دارد و قبل از رسیدن به این سقف بسته
            می‌شود. قیمت هر پلن نباید از «تعداد گفتگو × این سقف» کمتر شود؛ ذخیره‌ی پلنی که این را بشکند رد می‌شود. پلن
            سفارشی هر گفتگو را {formatToman(CUSTOM_PRICE_PER_CONVERSATION_TOMAN)} حساب می‌کند.
          </p>
          <UsdRateEditor initial={Number(rate?.value ?? 300000)} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {plans.map((plan) => (
          <Card key={plan.id}>
            <CardHeader>
              <CardTitle className="text-sm">{plan.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <PlanEditor
                plan={{
                  id: plan.id,
                  name: plan.name,
                  description: plan.description ?? "",
                  conversationsPerMonth: plan.conversationsPerMonth,
                  monthlyPriceToman: plan.monthlyPriceToman,
                  discountPercent3Months: plan.discountPercent3Months,
                  discountPercent12Months: plan.discountPercent12Months,
                  maxActiveProducts: plan.maxActiveProducts,
                  maxMonthlyProductUploads: plan.maxMonthlyProductUploads,
                  maxFaqItems: plan.maxFaqItems,
                  maxBroadcastsPerMonth: plan.maxBroadcastsPerMonth,
                  isActive: plan.isActive,
                }}
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

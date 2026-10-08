"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import {
  CUSTOM_CONVERSATION_STEP,
  CUSTOM_MAX_CONVERSATIONS,
  CUSTOM_MIN_CONVERSATIONS,
  CUSTOM_PLAN_KEY,
  PLAN_DURATIONS_MONTHS,
  clampCustomConversations,
  customPlanPrice,
  maxMonthlyCostToman,
  planPrice,
  type PlanDuration,
  type PlanPricing,
} from "@zify/shared"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ChoiceGroup } from "@/components/choice-group"
import { DURATION_LABELS, formatToman } from "@/lib/leads"

interface PlanOption extends PlanPricing {
  key: string
  name: string
  conversationsPerMonth: number
}

export function ActivateForm({
  shopId,
  plans,
  hasActive,
}: {
  shopId: string
  plans: PlanOption[]
  hasActive: boolean
}) {
  const router = useRouter()
  const [planKey, setPlanKey] = useState(plans[0]?.key ?? CUSTOM_PLAN_KEY)
  const [months, setMonths] = useState<PlanDuration>(1)
  const [customConversations, setCustomConversations] = useState(1000)
  const [note, setNote] = useState("")
  const [saving, setSaving] = useState(false)

  const plan = plans.find((p) => p.key === planKey)
  const isCustom = planKey === CUSTOM_PLAN_KEY
  const conversations = isCustom
    ? clampCustomConversations(customConversations)
    : (plan?.conversationsPerMonth ?? 0)
  const price = isCustom ? customPlanPrice(conversations, months) : plan ? planPrice(plan, months) : 0

  async function handleActivate() {
    setSaving(true)
    try {
      const res = await fetch(`/api/admin/shops/${shopId}/subscriptions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ planKey, months, conversationsPerMonth: conversations, note }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "خطا در فعال‌سازی")
      toast.success("اشتراک فعال شد")
      setNote("")
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در فعال‌سازی")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label>پلن</Label>
        <ChoiceGroup
          aria-label="پلن"
          value={planKey}
          onChange={setPlanKey}
          options={[
            ...plans.map((p) => ({ value: p.key, label: p.name })),
            { value: CUSTOM_PLAN_KEY, label: "سفارشی" },
          ]}
        />
      </div>

      {isCustom && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="custom-conversations">تعداد گفتگو در ماه</Label>
          <Input
            id="custom-conversations"
            type="number"
            dir="ltr"
            className="text-right"
            min={CUSTOM_MIN_CONVERSATIONS}
            max={CUSTOM_MAX_CONVERSATIONS}
            step={CUSTOM_CONVERSATION_STEP}
            value={customConversations}
            onChange={(e) => setCustomConversations(Number(e.target.value))}
          />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label>مدت</Label>
        <ChoiceGroup
          aria-label="مدت اشتراک"
          value={months}
          onChange={setMonths}
          options={PLAN_DURATIONS_MONTHS.map((m) => ({ value: m, label: DURATION_LABELS[m] }))}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="payment-note">یادداشت پرداخت</Label>
        <Textarea
          id="payment-note"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="مثال: کارت‌به‌کارت، شماره پیگیری ..."
        />
      </div>

      <div className="rounded-lg border bg-muted/30 p-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">مبلغ کل این دوره</span>
          <span className="font-bold">{formatToman(price)}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>گفتگو در ماه</span>
          <span>{conversations.toLocaleString("fa-IR")}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>حداکثر هزینه‌ی ما در کل دوره</span>
          <span>{formatToman(maxMonthlyCostToman(conversations) * months)}</span>
        </div>
      </div>

      {hasActive && (
        <p className="text-xs text-muted-foreground">
          با فعال‌سازی، اشتراک فعلی همین حالا پایان می‌یابد و اشتراک جدید از امروز شروع می‌شود.
        </p>
      )}

      <Button onClick={handleActivate} disabled={saving || price <= 0}>
        {saving ? "در حال فعال‌سازی..." : "فعال‌سازی پس از دریافت وجه"}
      </Button>
    </div>
  )
}

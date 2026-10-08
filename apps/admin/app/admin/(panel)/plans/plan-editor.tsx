"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { maxMonthlyCostToman } from "@zify/shared"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { formatToman } from "@/lib/leads"

interface EditablePlan {
  id: string
  name: string
  description: string
  conversationsPerMonth: number
  monthlyPriceToman: number
  discountPercent3Months: number
  discountPercent12Months: number
  maxActiveProducts: number
  maxMonthlyProductUploads: number
  maxFaqItems: number
  maxBroadcastsPerMonth: number
  isActive: boolean
}

const NUMBER_FIELDS: { key: keyof EditablePlan; label: string }[] = [
  { key: "conversationsPerMonth", label: "گفتگو در ماه" },
  { key: "monthlyPriceToman", label: "قیمت ماهانه (تومان)" },
  { key: "discountPercent3Months", label: "تخفیف سه‌ماهه (٪)" },
  { key: "discountPercent12Months", label: "تخفیف یک‌ساله (٪)" },
  { key: "maxActiveProducts", label: "محصول فعال" },
  { key: "maxMonthlyProductUploads", label: "افزودن و ویرایش محصول در ماه" },
  { key: "maxFaqItems", label: "سوال متداول" },
  { key: "maxBroadcastsPerMonth", label: "پیام همگانی در ماه" },
]

export function PlanEditor({ plan }: { plan: EditablePlan }) {
  const router = useRouter()
  const [form, setForm] = useState(plan)
  const [saving, setSaving] = useState(false)

  const costCeiling = maxMonthlyCostToman(form.conversationsPerMonth)

  async function handleSave() {
    setSaving(true)
    try {
      const res = await fetch(`/api/admin/plans/${plan.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "خطا در ذخیره")
      toast.success("پلن ذخیره شد")
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ذخیره")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${plan.id}-name`}>نام</Label>
        <Input
          id={`${plan.id}-name`}
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${plan.id}-description`}>توضیح کوتاه</Label>
        <Input
          id={`${plan.id}-description`}
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        {NUMBER_FIELDS.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1.5">
            <Label htmlFor={`${plan.id}-${key}`} className="text-xs">
              {label}
            </Label>
            <Input
              id={`${plan.id}-${key}`}
              type="number"
              min={0}
              dir="ltr"
              className="text-right"
              value={form[key] as number}
              onChange={(e) => setForm((f) => ({ ...f, [key]: Number(e.target.value) }))}
            />
          </div>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        حداکثر هزینه‌ی این تعداد گفتگو در ماه: {formatToman(costCeiling)}
      </p>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={form.isActive}
          onCheckedChange={(checked) => setForm((f) => ({ ...f, isActive: checked === true }))}
        />
        در صفحه‌ی قیمت‌ها نمایش داده شود
      </label>

      <Button onClick={handleSave} disabled={saving} className="self-start">
        {saving ? "در حال ذخیره..." : "ذخیره"}
      </Button>
    </div>
  )
}

"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function UsdRateEditor({ initial }: { initial: number }) {
  const router = useRouter()
  const [value, setValue] = useState(initial)
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      const res = await fetch("/api/admin/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usdToman: value }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "خطا در ذخیره")
      toast.success("نرخ دلار ذخیره شد")
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ذخیره")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="usd-rate">نرخ دلار (تومان)</Label>
      <div className="flex items-center gap-2">
        <Input
          id="usd-rate"
          type="number"
          min={1000}
          dir="ltr"
          className="max-w-44 text-right"
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
        />
        <Button size="sm" variant="outline" onClick={handleSave} disabled={saving || value === initial}>
          {saving ? "در حال ذخیره..." : "ذخیره"}
        </Button>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        هزینه‌ی واقعی هر گفتگو با این نرخ به تومان حساب می‌شود. سقف هزینه‌ی هر گفتگو و قیمت پلن‌ها با دلار ۳۰۰٬۰۰۰ تومان
        تنظیم شده‌اند؛ اگر دلار بالا رفت، قیمت پلن‌ها را هم به همان نسبت بالا ببرید.
      </p>
    </div>
  )
}

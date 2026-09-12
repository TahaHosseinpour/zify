"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { toast } from "sonner"

interface ShopForm {
  name: string
  description: string
  categories: string
  supportInfo: string
  personaCharacter: string
  personaTone: string
  systemPromptExtra: string
}

export default function BusinessPage() {
  const [form, setForm] = useState<ShopForm>({
    name: "", description: "", categories: "", supportInfo: "", personaCharacter: "", personaTone: "formal", systemPromptExtra: "",
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch("/api/shop")
      .then((r) => r.json())
      .then((shop) => {
        if (shop) {
          setForm({
            name: shop.name ?? "",
            description: shop.description ?? "",
            categories: (shop.categories ?? []).join("، "),
            supportInfo: shop.supportInfo?.text ?? "",
            personaCharacter: shop.personaCharacter ?? "",
            personaTone: shop.personaTone ?? "formal",
            systemPromptExtra: shop.systemPromptExtra ?? "",
          })
        }
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await fetch("/api/shop", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          categories: form.categories.split("،").map((c) => c.trim()).filter(Boolean),
          supportInfo: form.supportInfo ? { text: form.supportInfo } : null,
        }),
      })
      if (!res.ok) throw new Error()
      toast.success("اطلاعات ذخیره شد — embeddings در حال بروزرسانی")
    } catch { toast.error("خطا در ذخیره") } finally { setSaving(false) }
  }

  const f = (key: keyof ShopForm) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((prev) => ({ ...prev, [key]: e.target.value })),
  })

  if (loading) return <div className="flex flex-col gap-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">اطلاعات پایه</CardTitle>
          <CardDescription>این اطلاعات برای آموزش دستیار شما استفاده می‌شود</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>نام فروشگاه</Label>
            <Input {...f("name")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>توضیحات فروشگاه</Label>
            <Textarea {...f("description")} rows={3} placeholder="چه محصولاتی می‌فروشید؟ چه ارزشی ایجاد می‌کنید؟" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>دسته‌بندی‌ها (با ، جدا کنید)</Label>
            <Input {...f("categories")} placeholder="پوشاک، کیف، کفش" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>اطلاعات پشتیبانی</Label>
            <Textarea {...f("supportInfo")} rows={3} placeholder="ساعات پاسخگویی، روش ارسال، سیاست مرجوعی، گارانتی..." />
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">شخصیت دستیار</CardTitle>
          <CardDescription>این تنظیمات لحن و سبک پاسخ‌های دستیار را مشخص می‌کند</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>شخصیت دستیار</Label>
            <Input {...f("personaCharacter")} placeholder="مثال: دوستانه و متخصص، صمیمی، حرفه‌ای" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>لحن</Label>
            <Select value={form.personaTone} onValueChange={(v: string) => setForm((p) => ({ ...p, personaTone: v }))}>
              <SelectTrigger dir="rtl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent dir="rtl">
                <SelectItem value="formal">رسمی</SelectItem>
                <SelectItem value="semi-formal">نیمه‌رسمی</SelectItem>
                <SelectItem value="friendly">صمیمی</SelectItem>
                <SelectItem value="casual">خودمانی</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>دستورالعمل‌های اضافی (اختیاری)</Label>
            <Textarea {...f("systemPromptExtra")} rows={3} placeholder="هر دستورالعمل خاصی که می‌خواهید دستیار رعایت کند..." />
          </div>
        </CardContent>
      </Card>

      <Button type="submit" disabled={saving} className="w-full sm:w-auto">
        {saving ? "در حال ذخیره..." : "ذخیره تغییرات"}
      </Button>
    </form>
  )
}

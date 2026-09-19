"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogAction, AlertDialogCancel,
} from "@/components/ui/alert-dialog"
import { toast } from "sonner"

interface SettingsForm {
  slug: string
  name: string
  description: string
  categories: string
  supportInfo: string
  personaCharacter: string
  personaTone: string
  systemPromptExtra: string
}

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsForm>({
    slug: "", name: "", description: "", categories: "", supportInfo: "",
    personaCharacter: "", personaTone: "formal", systemPromptExtra: "",
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)

  const [hasPassword, setHasPassword] = useState(false)
  const [pwForm, setPwForm] = useState({ password: "", confirm: "" })
  const [savingPassword, setSavingPassword] = useState(false)

  async function handleSetPassword(e: React.FormEvent) {
    e.preventDefault()
    if (pwForm.password.length < 6) {
      toast.error("رمز عبور باید حداقل ۶ کاراکتر باشد")
      return
    }
    if (pwForm.password !== pwForm.confirm) {
      toast.error("رمز عبور و تکرار آن یکسان نیستند")
      return
    }
    setSavingPassword(true)
    try {
      const res = await fetch("/api/auth/set-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pwForm.password }),
      })
      if (!res.ok) throw new Error()
      toast.success("رمز عبور ذخیره شد")
      setHasPassword(true)
      setPwForm({ password: "", confirm: "" })
    } catch {
      toast.error("خطا در ذخیره رمز عبور")
    } finally {
      setSavingPassword(false)
    }
  }

  async function handleResetAgent() {
    setResetting(true)
    try {
      const res = await fetch("/api/agent/reset", { method: "POST" })
      const data = await res.json()
      if (!res.ok) throw new Error()
      if (data.warning) toast.warning(data.warning)
      else toast.success("دستیار ریست شد — اطلاعات جدید بازیابی شد")
    } catch {
      toast.error("خطا در ریست دستیار")
    } finally {
      setResetting(false)
    }
  }

  useEffect(() => {
    fetch("/api/shop")
      .then((r) => r.json())
      .then((shop) => {
        if (shop) {
          setForm({
            slug: shop.slug ?? "",
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

    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => setHasPassword(Boolean(me?.hasPassword)))
      .catch(() => {})
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
      const data = await res.json()
      if (!res.ok) throw new Error(data?.error)
      toast.success("تنظیمات ذخیره شد")
    } catch (err: unknown) {
      toast.error(err instanceof Error && err.message ? err.message : "خطا در ذخیره")
    } finally { setSaving(false) }
  }

  if (loading) return <div className="flex flex-col gap-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>

  function slugify(text: string) {
    return text
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "")
      .slice(0, 30)
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">اطلاعات کسب‌وکار</CardTitle>
          <CardDescription>این اطلاعات برای آموزش دستیار شما استفاده می‌شود</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>نام فروشگاه</Label>
            <Input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>توضیحات فروشگاه</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              rows={3}
              placeholder="چه محصولاتی می‌فروشید؟ چه ارزشی ایجاد می‌کنید؟"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>دسته‌بندی‌ها (با ، جدا کنید)</Label>
            <Input
              value={form.categories}
              onChange={(e) => setForm((p) => ({ ...p, categories: e.target.value }))}
              placeholder="پوشاک، کیف، کفش"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>اطلاعات پشتیبانی</Label>
            <Textarea
              value={form.supportInfo}
              onChange={(e) => setForm((p) => ({ ...p, supportInfo: e.target.value }))}
              rows={3}
              placeholder="ساعات پاسخگویی، روش ارسال، سیاست مرجوعی، گارانتی..."
            />
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">شناسه یکتا فروشگاه</CardTitle>
          <CardDescription>
            لینک تلگرام شما را می‌سازد: t.me/bot?start={form.slug || "shop-slug"} — تغییر آن یعنی
            لینک‌های قبلی که به مشتریان داده‌اید دیگر کار نمی‌کنند.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-1.5">
            <Label>شناسه یکتا (انگلیسی)</Label>
            <Input
              dir="ltr"
              value={form.slug}
              onChange={(e) => setForm((p) => ({ ...p, slug: slugify(e.target.value) }))}
            />
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">شخصیت دستیار فروش</CardTitle>
          <CardDescription>این تنظیمات نحوه پاسخگویی دستیار به مشتریان را تعیین می‌کند</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>شخصیت</Label>
            <Input
              value={form.personaCharacter}
              onChange={(e) => setForm((p) => ({ ...p, personaCharacter: e.target.value }))}
              placeholder="مثال: متخصص فروش با دانش بالا، صمیمی و کمک‌کننده"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>لحن پاسخ‌ها</Label>
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
            <Label>دستورالعمل‌های اضافی</Label>
            <Textarea
              value={form.systemPromptExtra}
              onChange={(e) => setForm((p) => ({ ...p, systemPromptExtra: e.target.value }))}
              rows={4}
              placeholder="هر دستورالعمل خاصی که می‌خواهید دستیار رعایت کند..."
            />
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">ریست دستیار</CardTitle>
          <CardDescription>
            اگر محصولات، سوالات متداول یا اطلاعات فروشگاه را تغییر داده‌اید، با این دکمه همه‌چیز
            دوباره ایندکس می‌شود و حافظه گفتگوهای دستیار پاک می‌شود تا اطلاعات جدید را بازیابی کند.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={() => setResetConfirmOpen(true)} disabled={resetting}>
            {resetting ? "در حال ریست..." : "ریست حافظه دستیار"}
          </Button>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{hasPassword ? "تغییر رمز عبور" : "تعیین رمز عبور"}</CardTitle>
          <CardDescription>برای ورود با شماره موبایل و رمز عبور.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>رمز عبور جدید</Label>
            <Input
              type="password"
              dir="ltr"
              className="text-left"
              placeholder="حداقل ۶ کاراکتر"
              value={pwForm.password}
              onChange={(e) => setPwForm((p) => ({ ...p, password: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>تکرار رمز عبور</Label>
            <Input
              type="password"
              dir="ltr"
              className="text-left"
              placeholder="رمز عبور را دوباره وارد کنید"
              value={pwForm.confirm}
              onChange={(e) => setPwForm((p) => ({ ...p, confirm: e.target.value }))}
            />
          </div>
          <Button type="button" variant="outline" onClick={handleSetPassword} disabled={savingPassword}>
            {savingPassword ? "در حال ذخیره..." : hasPassword ? "تغییر رمز عبور" : "تعیین رمز عبور"}
          </Button>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base text-destructive">خروج از حساب</CardTitle>
        </CardHeader>
        <CardContent>
          <Button
            type="button"
            variant="destructive"
            onClick={async () => {
              await fetch("/api/auth/logout", { method: "POST" })
              window.location.href = "/login"
            }}
          >
            خروج از پنل
          </Button>
        </CardContent>
      </Card>

      <Button type="submit" disabled={saving}>
        {saving ? "در حال ذخیره..." : "ذخیره تنظیمات"}
      </Button>

      <AlertDialog open={resetConfirmOpen} onOpenChange={setResetConfirmOpen}>
        <AlertDialogContent dir="rtl">
          <AlertDialogHeader>
            <AlertDialogTitle>ریست حافظه دستیار</AlertDialogTitle>
            <AlertDialogDescription>
              همه محصولات، سوالات متداول و اطلاعات فروشگاه دوباره ایندکس می‌شوند و حافظه
              گفتگوهای دستیار پاک می‌شود. ادامه می‌دهید؟
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>انصراف</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => { setResetConfirmOpen(false); handleResetAgent() }}
            >
              ادامه
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </form>
  )
}

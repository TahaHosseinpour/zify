"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"
import { motion, AnimatePresence } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { Store01Icon, LinkSquare01Icon, ShoppingBag01Icon, CheckmarkCircle01Icon } from "@hugeicons/core-free-icons"

const steps = [
  { title: "اطلاعات کسب‌وکار", icon: Store01Icon },
  { title: "اتصال کانال تلگرام", icon: LinkSquare01Icon },
  { title: "محصولات و سوالات", icon: ShoppingBag01Icon },
]

interface ShopData {
  name: string
  slug: string
  description: string
  categories: string
  supportInfo: string
  personaCharacter: string
  personaTone: string
}

export default function OnboardingPage() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [shopId, setShopId] = useState<string | null>(null)
  const [deepLink, setDeepLink] = useState<string | null>(null)

  const [shopData, setShopData] = useState<ShopData>({
    name: "",
    slug: "",
    description: "",
    categories: "",
    supportInfo: "",
    personaCharacter: "دوستانه و حرفه‌ای",
    personaTone: "formal",
  })

  function slugify(text: string) {
    return text
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "")
      .slice(0, 30)
  }

  async function handleStep1(e: React.FormEvent) {
    e.preventDefault()
    if (!shopData.name || !shopData.slug) {
      toast.error("نام و شناسه فروشگاه الزامی است")
      return
    }
    setLoading(true)
    try {
      const res = await fetch("/api/shop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...shopData,
          categories: shopData.categories.split("،").map((c) => c.trim()).filter(Boolean),
          supportInfo: shopData.supportInfo ? { text: shopData.supportInfo } : null,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setShopId(data.id)
      setStep(1)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "خطا در ذخیره اطلاعات")
    } finally {
      setLoading(false)
    }
  }

  async function handleStep2(e: React.FormEvent) {
    e.preventDefault()
    if (!shopId) return
    setLoading(true)
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shopId }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setDeepLink(data.deepLink)
      setStep(2)
    } catch {
      toast.error("خطا در ساخت کانال")
    } finally {
      setLoading(false)
    }
  }

  async function handleFinish() {
    setLoading(true)
    try {
      const res = await fetch("/api/shop/complete-onboarding", { method: "POST" })
      if (!res.ok) throw new Error()
      router.push("/dashboard")
    } catch {
      toast.error("خطا در تکمیل آنبوردینگ")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-xl flex flex-col gap-6">
        {/* Header */}
        <div className="flex flex-col items-center gap-1">
          <Image src="/logo.png" alt="Zify" width={48} height={48} className="rounded-full mb-1" />
          <h1 className="text-2xl font-bold text-primary">Zify</h1>
          <p className="text-muted-foreground text-sm">راه‌اندازی فروشگاه شما</p>
        </div>

        {/* Progress */}
        <div className="flex flex-col gap-2">
          <Progress value={((step + 1) / steps.length) * 100} className="h-2" />
          <div className="flex justify-between">
            {steps.map((s, i) => (
              <div key={i} className={`flex items-center gap-1 text-xs ${i <= step ? "text-primary" : "text-muted-foreground"}`}>
                <HugeiconsIcon icon={i < step ? CheckmarkCircle01Icon : s.icon} className="size-4" />
                <span className="hidden sm:inline">{s.title}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Steps */}
        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div key="step0" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
              <Card>
                <CardHeader>
                  <CardTitle>اطلاعات کسب‌وکار</CardTitle>
                  <CardDescription>اطلاعات پایه فروشگاه خود را وارد کنید</CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleStep1} className="flex flex-col gap-4">
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="name">نام فروشگاه *</Label>
                      <Input
                        id="name"
                        placeholder="مثال: فروشگاه پوشاک آرین"
                        value={shopData.name}
                        onChange={(e) => setShopData(d => ({
                          ...d,
                          name: e.target.value,
                          slug: slugify(e.target.value),
                        }))}
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="slug">شناسه یکتا (انگلیسی) *</Label>
                      <Input
                        id="slug"
                        placeholder="aryan-shop"
                        dir="ltr"
                        value={shopData.slug}
                        onChange={(e) => setShopData(d => ({ ...d, slug: slugify(e.target.value) }))}
                      />
                      <p className="text-xs text-muted-foreground">لینک تلگرام: t.me/bot?start={shopData.slug || "shop-slug"}</p>
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="description">توضیحات فروشگاه</Label>
                      <Textarea
                        id="description"
                        placeholder="چه محصولاتی می‌فروشید؟"
                        value={shopData.description}
                        onChange={(e) => setShopData(d => ({ ...d, description: e.target.value }))}
                        rows={3}
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="categories">دسته‌بندی‌ها (با ، جدا کنید)</Label>
                      <Input
                        id="categories"
                        placeholder="پوشاک، کیف، کفش"
                        value={shopData.categories}
                        onChange={(e) => setShopData(d => ({ ...d, categories: e.target.value }))}
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="support">اطلاعات پشتیبانی</Label>
                      <Textarea
                        id="support"
                        placeholder="ساعات پاسخگویی، روش ارسال، سیاست مرجوعی..."
                        value={shopData.supportInfo}
                        onChange={(e) => setShopData(d => ({ ...d, supportInfo: e.target.value }))}
                        rows={2}
                      />
                    </div>
                    <Button type="submit" disabled={loading} className="w-full">
                      {loading ? "در حال ذخیره..." : "بعدی"}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div key="step1" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
              <Card>
                <CardHeader>
                  <CardTitle>اتصال کانال تلگرام</CardTitle>
                  <CardDescription>دستیار شما از طریق این لینک در دسترس مشتریان خواهد بود</CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleStep2} className="flex flex-col gap-4">
                    <p className="text-sm text-muted-foreground">
                      با کلیک روی دکمه زیر، کانال تلگرام شما ساخته می‌شود و لینک اختصاصی دریافت می‌کنید.
                    </p>
                    <Button type="submit" disabled={loading} className="w-full">
                      {loading ? "در حال ساخت..." : "ساخت کانال و دریافت لینک"}
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => setStep(0)}>
                      برگشت
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div key="step2" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
              <Card>
                <CardHeader>
                  <CardTitle>آماده‌اید! 🎉</CardTitle>
                  <CardDescription>فروشگاه شما با موفقیت ساخته شد</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {deepLink && (
                    <div className="bg-accent rounded-lg p-4 flex flex-col gap-2">
                      <p className="text-sm font-medium">لینک اختصاصی تلگرام:</p>
                      <code dir="ltr" className="text-sm text-primary break-all">{deepLink}</code>
                    </div>
                  )}
                  <p className="text-sm text-muted-foreground">
                    می‌توانید از داشبورد، محصولات و سوالات متداول را اضافه کنید.
                  </p>
                  <Button onClick={handleFinish} disabled={loading} className="w-full">
                    {loading ? "در حال ورود..." : "ورود به داشبورد"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

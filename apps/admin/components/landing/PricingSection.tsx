"use client"

import { useState } from "react"
import { toast } from "sonner"
import {
  CUSTOM_CONVERSATION_STEP,
  CUSTOM_MIN_CONVERSATIONS,
  CUSTOM_PLAN_KEY,
  PLAN_DURATIONS_MONTHS,
  customPlanPrice,
  planPrice,
  type PlanDuration,
  type PlanPricing,
} from "@zify/shared"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Toaster } from "@/components/ui/sonner"
import { ChoiceGroup } from "@/components/choice-group"
import { DURATION_LABELS, formatToman } from "@/lib/leads"
import { cn } from "@/lib/utils"

export interface PricingPlan extends PlanPricing {
  key: string
  name: string
  description: string | null
  conversationsPerMonth: number
  maxActiveProducts: number
  maxFaqItems: number
  maxBroadcastsPerMonth: number
}

interface Selection {
  planKey: string
  planName: string
  conversationsPerMonth: number
  totalPrice: number
}

// How far the slider goes. Larger shops exist, but past this point a
// conversation with us is worth more than a slider position.
const SLIDER_MAX_CONVERSATIONS = 20_000
const DAYS_PER_MONTH = 30

const fa = (n: number) => Math.round(n).toLocaleString("fa-IR")

/** "about N customers a day" - the unit a shop owner actually thinks in. */
function perDay(conversationsPerMonth: number): string {
  return fa(Math.max(1, Math.round(conversationsPerMonth / DAYS_PER_MONTH)))
}

const EMPTY_FORM = { fullName: "", mobile: "", shopName: "", shopUrl: "", message: "" }

export default function PricingSection({ plans }: { plans: PricingPlan[] }) {
  const [months, setMonths] = useState<PlanDuration>(1)
  const [customConversations, setCustomConversations] = useState(1_500)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  const customTotal = customPlanPrice(customConversations, months)

  function open(next: Selection) {
    setSent(false)
    setSelection(next)
  }

  async function handleSubmit() {
    if (!selection) return
    if (!form.fullName.trim() || !form.shopName.trim() || !form.mobile.trim()) {
      toast.error("نام، شماره موبایل و نام فروشگاه را وارد کنید")
      return
    }
    setSending(true)
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          planKey: selection.planKey,
          months,
          conversationsPerMonth: selection.conversationsPerMonth,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "ثبت درخواست ناموفق بود")
      setSent(true)
      setForm(EMPTY_FORM)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "ثبت درخواست ناموفق بود")
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
      <div className="mb-10 flex flex-col items-center gap-3">
        <ChoiceGroup
          aria-label="مدت اشتراک"
          value={months}
          onChange={setMonths}
          options={PLAN_DURATIONS_MONTHS.map((m) => ({ value: m, label: DURATION_LABELS[m] }))}
        />
        <p className="text-xs text-muted-foreground">
          بدون دوره‌ی آزمایشی؛ اشتراک پس از هماهنگی و پرداخت فعال می‌شود.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {plans.map((plan, index) => {
          const total = planPrice(plan, months)
          const featured = index === 0
          return (
            <article
              key={plan.key}
              className={cn(
                "flex flex-col rounded-2xl border bg-card p-6",
                featured ? "border-primary/40 shadow-lg shadow-primary/5" : "border-border",
              )}
            >
              <h2 className="text-lg font-bold text-foreground">{plan.name}</h2>
              {plan.description && <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>}

              <div className="mt-6">
                <span className="text-3xl font-black text-foreground">{fa(total / months)}</span>
                <span className="ms-1 text-sm text-muted-foreground">تومان در ماه</span>
              </div>
              <p className="mt-1 h-5 text-xs text-muted-foreground">
                {months > 1 && `پرداخت ${DURATION_LABELS[months]}: ${formatToman(total)}`}
              </p>

              <ul className="mt-6 flex flex-1 flex-col gap-2.5 text-sm text-foreground">
                <li>
                  <strong>{fa(plan.conversationsPerMonth)} گفتگو</strong> در ماه
                  <span className="text-muted-foreground">، حدود {perDay(plan.conversationsPerMonth)} مشتری در روز</span>
                </li>
                <li>تا {fa(plan.maxActiveProducts)} محصول فعال</li>
                <li>تا {fa(plan.maxFaqItems)} سوال متداول</li>
                <li>{fa(plan.maxBroadcastsPerMonth)} پیام همگانی در ماه</li>
                <li>چت سایت و ربات تلگرام</li>
              </ul>

              <Button
                className="mt-7"
                variant={featured ? "default" : "outline"}
                onClick={() =>
                  open({
                    planKey: plan.key,
                    planName: plan.name,
                    conversationsPerMonth: plan.conversationsPerMonth,
                    totalPrice: total,
                  })
                }
              >
                درخواست این پلن
              </Button>
            </article>
          )
        })}

        <article className="flex flex-col rounded-2xl border border-dashed border-border bg-card p-6">
          <h2 className="text-lg font-bold text-foreground">سفارشی</h2>
          <p className="mt-1 text-sm text-muted-foreground">تعداد گفتگو را خودتان تعیین کنید</p>

          <div className="mt-6">
            <span className="text-3xl font-black text-foreground">{fa(customTotal / months)}</span>
            <span className="ms-1 text-sm text-muted-foreground">تومان در ماه</span>
          </div>
          <p className="mt-1 h-5 text-xs text-muted-foreground">
            {months > 1 && `پرداخت ${DURATION_LABELS[months]}: ${formatToman(customTotal)}`}
          </p>

          <div className="mt-6 flex flex-1 flex-col gap-3">
            <Label htmlFor="custom-conversations" className="text-sm font-normal text-foreground">
              <strong>{fa(customConversations)} گفتگو</strong> در ماه
              <span className="text-muted-foreground">، حدود {perDay(customConversations)} مشتری در روز</span>
            </Label>
            <input
              id="custom-conversations"
              type="range"
              min={CUSTOM_MIN_CONVERSATIONS}
              max={SLIDER_MAX_CONVERSATIONS}
              step={CUSTOM_CONVERSATION_STEP}
              value={customConversations}
              onChange={(e) => setCustomConversations(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{fa(CUSTOM_MIN_CONVERSATIONS)}</span>
              <span>{fa(SLIDER_MAX_CONVERSATIONS)}</span>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              برای بیش از {fa(SLIDER_MAX_CONVERSATIONS)} گفتگو در ماه، عدد موردنظرتان را در توضیحات درخواست بنویسید.
            </p>
          </div>

          <Button
            className="mt-7"
            variant="outline"
            onClick={() =>
              open({
                planKey: CUSTOM_PLAN_KEY,
                planName: "سفارشی",
                conversationsPerMonth: customConversations,
                totalPrice: customTotal,
              })
            }
          >
            درخواست پلن سفارشی
          </Button>
        </article>
      </div>

      <div className="mt-12 rounded-2xl border border-border bg-card p-6 text-sm leading-relaxed text-muted-foreground">
        <h2 className="mb-2 text-base font-bold text-foreground">گفتگو چطور شمرده می‌شود؟</h2>
        <p>
          هر مشتری که به دستیار شما پیام می‌دهد یک گفتگو حساب می‌شود و می‌تواند در همان گفتگو تا ۸ پیام بفرستد. اگر
          بیشتر ادامه بدهد، گفتگوی بعدی شروع می‌شود. باز کردن صفحه‌ی چت بدون فرستادن پیام چیزی از سهمیه‌ی شما کم
          نمی‌کند. با تمام شدن گفتگوهای ماه یا پایان مدت اشتراک، دستیار تا تمدید خاموش می‌ماند.
        </p>
      </div>

      <Dialog open={selection !== null} onOpenChange={(isOpen) => !isOpen && setSelection(null)}>
        <DialogContent dir="rtl" className="max-w-md">
          {sent ? (
            <>
              <DialogHeader>
                <DialogTitle>درخواست شما ثبت شد</DialogTitle>
                <DialogDescription>
                  به‌زودی برای هماهنگی جلسه و فعال‌سازی با شماره‌ای که وارد کردید تماس می‌گیریم.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button onClick={() => setSelection(null)}>بستن</Button>
              </DialogFooter>
            </>
          ) : (
            selection && (
              <>
                <DialogHeader>
                  <DialogTitle>درخواست پلن {selection.planName}</DialogTitle>
                  <DialogDescription>
                    {DURATION_LABELS[months]}، {fa(selection.conversationsPerMonth)} گفتگو در ماه،{" "}
                    {formatToman(selection.totalPrice)}
                  </DialogDescription>
                </DialogHeader>
                <DialogBody className="flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="lead-name">نام و نام خانوادگی *</Label>
                    <Input
                      id="lead-name"
                      value={form.fullName}
                      onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                      autoComplete="name"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="lead-mobile">شماره موبایل *</Label>
                    <Input
                      id="lead-mobile"
                      type="tel"
                      dir="ltr"
                      className="text-right"
                      placeholder="09xxxxxxxxx"
                      value={form.mobile}
                      onChange={(e) => setForm((f) => ({ ...f, mobile: e.target.value }))}
                      autoComplete="tel"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="lead-shop">نام فروشگاه *</Label>
                    <Input
                      id="lead-shop"
                      value={form.shopName}
                      onChange={(e) => setForm((f) => ({ ...f, shopName: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="lead-url">آدرس سایت یا صفحه‌ی اینستاگرام</Label>
                    <Input
                      id="lead-url"
                      dir="ltr"
                      className="text-right"
                      value={form.shopUrl}
                      onChange={(e) => setForm((f) => ({ ...f, shopUrl: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="lead-message">توضیحات</Label>
                    <Textarea
                      id="lead-message"
                      rows={3}
                      value={form.message}
                      onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
                      placeholder="هر چیزی که لازم است قبل از تماس بدانیم"
                    />
                  </div>
                </DialogBody>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setSelection(null)}>
                    انصراف
                  </Button>
                  <Button onClick={handleSubmit} disabled={sending}>
                    {sending ? "در حال ثبت..." : "ثبت درخواست"}
                  </Button>
                </DialogFooter>
              </>
            )
          )}
        </DialogContent>
      </Dialog>
      <Toaster />
    </section>
  )
}

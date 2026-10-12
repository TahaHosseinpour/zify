"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { Copy01Icon, TelegramIcon, CodeIcon } from "@hugeicons/core-free-icons"

type ChannelType = "telegram" | "widget"

interface ChannelsState {
  slug: string
  telegram: { active: boolean; link: string }
  widget: { active: boolean }
}

function copy(text: string, message: string) {
  navigator.clipboard.writeText(text)
  toast.success(message)
}

export default function ChannelsPage() {
  const [state, setState] = useState<ChannelsState | null>(null)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState<ChannelType | null>(null)

  useEffect(() => {
    fetch("/api/channels")
      .then((r) => (r.ok ? r.json() : null))
      .then(setState)
      .finally(() => setLoading(false))
  }, [])

  async function toggle(type: ChannelType, active: boolean) {
    setPending(type)
    try {
      const res = await fetch("/api/channels", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, active }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.error)
      setState((prev) => (prev ? { ...prev, [type]: { ...prev[type], active } } : prev))
      toast.success(active ? "کانال فعال شد" : "کانال غیرفعال شد")
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "خطا در تغییر وضعیت کانال")
    } finally {
      setPending(null)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        {Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-40 rounded-xl" />)}
      </div>
    )
  }
  if (!state) return <div className="py-12 text-center text-muted-foreground">فروشگاهی پیدا نشد</div>

  // The script is served by this same site, wherever it is deployed. Only
  // reached in the browser: everything above returns until the fetch lands.
  const embedCode = `<script src="${window.location.origin}/widget.js" data-shop="${state.slug}" async></script>`

  function toggleButton(type: ChannelType) {
    const active = state![type].active
    return (
      <Button
        size="sm"
        variant={active ? "outline" : "default"}
        disabled={pending === type}
        onClick={() => toggle(type, !active)}
      >
        {pending === type ? "در حال ذخیره..." : active ? "غیرفعال کردن" : "فعال کردن"}
      </Button>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <HugeiconsIcon icon={TelegramIcon} className="size-4 text-primary" />
              تلگرام
              <Badge variant={state.telegram.active ? "default" : "secondary"}>
                {state.telegram.active ? "فعال" : "غیرفعال"}
              </Badge>
            </CardTitle>
            <CardDescription>مشتری با باز کردن لینک فروشگاه شما، در تلگرام با دستیار گفت‌وگو می‌کند.</CardDescription>
          </div>
          {toggleButton("telegram")}
        </CardHeader>
        {state.telegram.active && (
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3 rounded-lg bg-accent p-3">
              <div className="min-w-0">
                <p className="mb-1 text-xs text-muted-foreground">لینک فروشگاه شما</p>
                <code dir="ltr" className="block truncate text-sm text-primary">{state.telegram.link}</code>
              </div>
              <Button size="icon-sm" variant="ghost" aria-label="کپی لینک" onClick={() => copy(state.telegram.link, "لینک کپی شد")}>
                <HugeiconsIcon icon={Copy01Icon} />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              لینک اختصاصی هر محصول را از صفحه «محصولات»، با دکمه کپی لینک همان ردیف بردارید.
            </p>
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <HugeiconsIcon icon={CodeIcon} className="size-4 text-primary" />
              ویجت سایت
              <Badge variant={state.widget.active ? "default" : "secondary"}>
                {state.widget.active ? "فعال" : "غیرفعال"}
              </Badge>
            </CardTitle>
            <CardDescription>یک دکمه گفت‌وگو گوشه سایت خودتان؛ مشتری بدون ترک سایت با دستیار حرف می‌زند.</CardDescription>
          </div>
          {toggleButton("widget")}
        </CardHeader>
        {state.widget.active && (
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3 rounded-lg bg-accent p-3">
              <div className="min-w-0">
                <p className="mb-1 text-xs text-muted-foreground">کد ویجت</p>
                <code dir="ltr" className="block break-all text-left text-sm text-primary">{embedCode}</code>
              </div>
              <Button size="icon-sm" variant="ghost" aria-label="کپی کد" onClick={() => copy(embedCode, "کد ویجت کپی شد")}>
                <HugeiconsIcon icon={Copy01Icon} />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              این کد را در همه صفحه‌های سایت، درست قبل از <code dir="ltr">&lt;/body&gt;</code> قرار دهید. برای
              نمایش دکمه در سمت چپ، <code dir="ltr">data-position=&quot;left&quot;</code> را به آن اضافه کنید.
            </p>
          </CardContent>
        )}
      </Card>
    </div>
  )
}

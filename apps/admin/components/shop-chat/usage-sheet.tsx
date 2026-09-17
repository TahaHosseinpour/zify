"use client"

import { useEffect, useState } from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Progress } from "@/components/ui/progress"

interface UsageStatus {
  weeklyUsed: number
  weeklyLimit: number
  weeklyResetAt: string | null
  monthlyUsed: number
  monthlyLimit: number
  monthlyResetAt: string | null
}

function pct(used: number, limit: number): number {
  return Math.min(100, Math.round((used / limit) * 100))
}

function formatReset(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("fa-IR")
}

export function UsageSheet({
  slug,
  webVisitorId,
  open,
  onOpenChange,
}: {
  slug: string
  webVisitorId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [status, setStatus] = useState<UsageStatus | null>(null)

  useEffect(() => {
    if (!open || !webVisitorId) return
    fetch(`/api/shop-chat/usage?slug=${encodeURIComponent(slug)}&webVisitorId=${encodeURIComponent(webVisitorId)}`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [open, slug, webVisitorId])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left">
        <SheetHeader>
          <SheetTitle>سقف مصرف شما</SheetTitle>
        </SheetHeader>
        {status && (
          <div className="flex flex-col gap-6 px-4">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-sm">
                <span>هفتگی</span>
                <span className="text-muted-foreground">
                  {status.weeklyUsed.toLocaleString("fa-IR")} از {status.weeklyLimit.toLocaleString("fa-IR")} توکن
                </span>
              </div>
              <Progress value={pct(status.weeklyUsed, status.weeklyLimit)} />
              <p className="text-xs text-muted-foreground">بازنشانی: {formatReset(status.weeklyResetAt)}</p>
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-sm">
                <span>ماهانه</span>
                <span className="text-muted-foreground">
                  {status.monthlyUsed.toLocaleString("fa-IR")} از {status.monthlyLimit.toLocaleString("fa-IR")} توکن
                </span>
              </div>
              <Progress value={pct(status.monthlyUsed, status.monthlyLimit)} />
              <p className="text-xs text-muted-foreground">بازنشانی: {formatReset(status.monthlyResetAt)}</p>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

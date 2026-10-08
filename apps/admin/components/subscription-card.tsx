"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type SubscriptionStatus =
  | { active: false }
  | {
      active: true
      planName: string
      endsAt: string
      daysLeft: number
      periodEnd: string | null
      conversationsUsed: number
      conversationsLimit: number
    }

// From here on the owner should be thinking about renewing or upgrading.
const WARN_AT_PERCENT = 80
const WARN_AT_DAYS_LEFT = 3

/** The owner's subscription at a glance: is the assistant on, how much of
 * this month's conversations are gone, and when it all ends. */
export function SubscriptionCard() {
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)

  useEffect(() => {
    fetch("/api/subscription")
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])

  if (status === null) return <Skeleton className="h-24 rounded-xl" />

  if (!status.active) {
    return (
      <Card className="border-destructive/30 bg-destructive/5">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold">دستیار شما خاموش است</p>
            <p className="text-sm text-muted-foreground">
              این فروشگاه اشتراک فعالی ندارد، پس دستیار به مشتری‌ها پاسخ نمی‌دهد. می‌توانید محصولات و سوالات متداول را
              از همین حالا آماده کنید.
            </p>
          </div>
          <Button asChild size="sm" className="shrink-0">
            <Link href="/pricing">مشاهده پلن‌ها</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  const used = status.conversationsUsed
  const limit = status.conversationsLimit
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100
  const daysLeft = status.daysLeft
  const exhausted = used >= limit
  const warn = exhausted || percent >= WARN_AT_PERCENT || daysLeft <= WARN_AT_DAYS_LEFT

  return (
    <Card className={cn(warn && "border-amber-500/40")}>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="font-semibold">پلن {status.planName}</span>
          <span className="text-muted-foreground">
            {daysLeft.toLocaleString("fa-IR")} روز تا پایان اشتراک (
            {new Date(status.endsAt).toLocaleDateString("fa-IR")})
          </span>
        </div>
        <Progress value={percent} />
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {used.toLocaleString("fa-IR")} از {limit.toLocaleString("fa-IR")} گفتگوی این دوره مصرف شده
          </span>
          {status.periodEnd && (
            <span>شروع دوره‌ی بعد: {new Date(status.periodEnd).toLocaleDateString("fa-IR")}</span>
          )}
        </div>
        {exhausted ? (
          <p className="text-sm text-destructive">
            گفتگوهای این دوره تمام شده و دستیار تا شروع دوره‌ی بعد یا ارتقای پلن خاموش است.
          </p>
        ) : (
          warn && (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              {daysLeft <= WARN_AT_DAYS_LEFT
                ? "اشتراک شما رو به پایان است. برای اینکه دستیار خاموش نشود، برای تمدید با ما هماهنگ کنید."
                : "بیشتر گفتگوهای این دوره مصرف شده است. اگر زودتر تمام شود، دستیار تا دوره‌ی بعد خاموش می‌ماند."}
            </p>
          )
        )}
      </CardContent>
    </Card>
  )
}

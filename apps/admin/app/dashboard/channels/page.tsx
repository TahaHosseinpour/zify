"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Copy01Icon, LinkSquare01Icon } from "@hugeicons/core-free-icons"

interface Channel {
  id: string
  type: string
  isActive: boolean
  createdAt: string
  deepLink: string
  exploreLink: string
}

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [shopSlug, setShopSlug] = useState("")

  useEffect(() => {
    Promise.all([
      fetch("/api/channels").then((r) => r.json()),
      fetch("/api/shop").then((r) => r.json()),
    ]).then(([ch, shop]) => {
      setChannels(ch)
      setShopSlug(shop?.slug ?? "")
    }).finally(() => setLoading(false))
  }, [])

  async function handleCreate() {
    setCreating(true)
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error()
      toast.success("کانال ساخته شد")
      const updated = await fetch("/api/channels").then((r) => r.json())
      setChannels(updated)
    } catch { toast.error("خطا در ساخت کانال") } finally { setCreating(false) }
  }

  function copyLink(link: string) {
    navigator.clipboard.writeText(link)
    toast.success("لینک کپی شد")
  }

  const botUsername = process.env.NEXT_PUBLIC_BOT_USERNAME || "ZifyBot"

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-end">
        <Button size="sm" onClick={handleCreate} disabled={creating}>
          <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
          {creating ? "در حال ساخت..." : "کانال جدید"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <HugeiconsIcon icon={LinkSquare01Icon} className="size-4 text-primary" />
            لینک‌های اختصاصی
          </CardTitle>
          <CardDescription>این لینک‌ها را برای مشتریان خود ارسال کنید</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {shopSlug && (
            <>
              <div className="flex items-center justify-between gap-3 bg-accent rounded-lg p-3">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">لینک مشاوره عمومی</p>
                  <code dir="ltr" className="text-sm text-primary">t.me/{botUsername}?start={shopSlug}</code>
                </div>
                <Button size="icon-sm" variant="ghost" onClick={() => copyLink(`https://t.me/${botUsername}?start=${shopSlug}`)}>
                  <HugeiconsIcon icon={Copy01Icon} />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                برای هر محصول، لینک اختصاصی: <code dir="ltr">t.me/{botUsername}?start={shopSlug}_[product-id]</code>
              </p>
            </>
          )}
        </CardContent>
      </Card>

      <Separator />

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : channels.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">هنوز کانالی ساخته نشده</div>
      ) : (
        <div className="flex flex-col gap-3">
          {channels.map((ch, i) => (
            <motion.div key={ch.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card>
                <CardContent className="flex items-center justify-between gap-4 p-4">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <Badge variant={ch.isActive ? "default" : "secondary"}>
                        {ch.isActive ? "فعال" : "غیرفعال"}
                      </Badge>
                      <span className="text-sm text-muted-foreground">تلگرام</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      ایجاد: {new Date(ch.createdAt).toLocaleDateString("fa-IR")}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

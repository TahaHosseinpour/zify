"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogBody, DialogFooter,
} from "@/components/ui/dialog"
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogAction, AlertDialogCancel,
} from "@/components/ui/alert-dialog"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { UserMultiple02Icon, Megaphone01Icon } from "@hugeicons/core-free-icons"

// Mirrors apps/agent/app/usage.py / packages/db/src/usage.ts - shown as a
// plain percentage of the stored counters. Not lazy-reset-adjusted here (that
// only happens server-side, in increment_input_tokens, the next time this
// end user actually chats) - a dashboard glance doesn't need to be that
// precise, and it self-corrects on the customer's next message regardless.
const WEEKLY_INPUT_TOKEN_LIMIT = 20_000
const MONTHLY_INPUT_TOKEN_LIMIT = 40_000

interface EndUser {
  id: string
  telegramUserId: string
  firstName: string | null
  username: string | null
  createdAt: string
  _count: { conversations: number }
  weeklyInputTokens: number
  weeklyResetAt: string
  monthlyInputTokens: number
  monthlyResetAt: string
}

function usagePct(used: number, limit: number): number {
  return Math.min(100, Math.round((used / limit) * 100))
}

export default function UsersPage() {
  const [users, setUsers] = useState<EndUser[]>([])
  const [loading, setLoading] = useState(true)
  const [broadcastOpen, setBroadcastOpen] = useState(false)
  const [broadcastConfirmOpen, setBroadcastConfirmOpen] = useState(false)
  const [broadcastMessage, setBroadcastMessage] = useState("")
  const [sending, setSending] = useState(false)

  const telegramUserCount = users.filter((u) => u.telegramUserId).length

  useEffect(() => {
    fetch("/api/users")
      .then((r) => r.json())
      .then(setUsers)
      .finally(() => setLoading(false))
  }, [])

  async function handleBroadcast() {
    setSending(true)
    try {
      const res = await fetch("/api/broadcast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: broadcastMessage }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      toast.success(`پیام برای ${data.sent.toLocaleString("fa-IR")} از ${data.total.toLocaleString("fa-IR")} کاربر ارسال شد`)
      setBroadcastMessage("")
      setBroadcastOpen(false)
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "خطا در ارسال پیام")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Button size="sm" onClick={() => setBroadcastOpen(true)} disabled={telegramUserCount === 0}>
          <HugeiconsIcon icon={Megaphone01Icon} data-icon="inline-start" />
          ارسال پیام گروهی
        </Button>
        <span className="text-sm text-muted-foreground">
          {users.length.toLocaleString("fa-IR")} کاربر
        </span>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex flex-col gap-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
            </div>
          ) : users.length === 0 ? (
            <div className="py-20 flex flex-col items-center gap-3 text-muted-foreground">
              <HugeiconsIcon icon={UserMultiple02Icon} className="size-12 opacity-30" />
              <p>هنوز کاربری وجود ندارد</p>
              <p className="text-sm">پس از اتصال تلگرام و شروع گفت‌وگو، کاربران اینجا نمایش داده می‌شوند</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>کاربر</TableHead>
                  <TableHead>آی‌دی تلگرام</TableHead>
                  <TableHead>گفت‌وگوها</TableHead>
                  <TableHead>سقف هفتگی</TableHead>
                  <TableHead>سقف ماهانه</TableHead>
                  <TableHead>تاریخ ثبت</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u, i) => {
                  const weeklyPct = usagePct(u.weeklyInputTokens, WEEKLY_INPUT_TOKEN_LIMIT)
                  const monthlyPct = usagePct(u.monthlyInputTokens, MONTHLY_INPUT_TOKEN_LIMIT)
                  return (
                    <motion.tr
                      key={u.id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="border-b last:border-0"
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Avatar className="size-8">
                            <AvatarFallback className="text-xs">
                              {(u.firstName ?? u.username ?? "؟")[0]}
                            </AvatarFallback>
                          </Avatar>
                          <div>
                            <p className="text-sm font-medium">{u.firstName ?? "—"}</p>
                            {u.username && (
                              <p className="text-xs text-muted-foreground" dir="ltr">@{u.username}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{u.telegramUserId}</TableCell>
                      <TableCell>{u._count.conversations.toLocaleString("fa-IR")}</TableCell>
                      <TableCell className="w-32">
                        <div className="flex flex-col gap-1">
                          <Progress value={weeklyPct} className="h-1.5" />
                          <span className="text-xs text-muted-foreground">
                            {weeklyPct.toLocaleString("fa-IR")}٪
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="w-32">
                        <div className="flex flex-col gap-1">
                          <Progress value={monthlyPct} className="h-1.5" />
                          <span className="text-xs text-muted-foreground">
                            {monthlyPct.toLocaleString("fa-IR")}٪
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(u.createdAt).toLocaleDateString("fa-IR")}
                      </TableCell>
                    </motion.tr>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={broadcastOpen} onOpenChange={(open) => !sending && setBroadcastOpen(open)}>
        <DialogContent dir="rtl">
          <DialogHeader>
            <DialogTitle>ارسال پیام گروهی</DialogTitle>
            <DialogDescription>
              این پیام برای همه کاربران بات تلگرام شما ({telegramUserCount.toLocaleString("fa-IR")} نفر) ارسال می‌شود.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <Textarea
              value={broadcastMessage}
              onChange={(e) => setBroadcastMessage(e.target.value)}
              rows={6}
              placeholder="متن پیام را بنویسید..."
              disabled={sending}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBroadcastOpen(false)} disabled={sending}>انصراف</Button>
            <Button
              onClick={() => setBroadcastConfirmOpen(true)}
              disabled={sending || !broadcastMessage.trim()}
            >
              {sending ? "در حال ارسال..." : "ارسال"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={broadcastConfirmOpen} onOpenChange={setBroadcastConfirmOpen}>
        <AlertDialogContent dir="rtl">
          <AlertDialogHeader>
            <AlertDialogTitle>ارسال پیام برای {telegramUserCount.toLocaleString("fa-IR")} کاربر؟</AlertDialogTitle>
            <AlertDialogDescription>
              این پیام بلافاصله و بدون امکان لغو برای همه کاربران تلگرام فروشگاه ارسال می‌شود.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>انصراف</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { setBroadcastConfirmOpen(false); handleBroadcast() }}
            >
              ارسال کن
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

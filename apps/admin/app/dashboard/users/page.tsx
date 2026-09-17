"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Progress } from "@/components/ui/progress"
import { HugeiconsIcon } from "@hugeicons/react"
import { UserMultiple02Icon } from "@hugeicons/core-free-icons"

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

  useEffect(() => {
    fetch("/api/users")
      .then((r) => r.json())
      .then(setUsers)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
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
                      <TableCell dir="ltr" className="text-sm text-muted-foreground">{u.telegramUserId}</TableCell>
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
    </div>
  )
}

"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar,
} from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  UserMultiple02Icon, MessageMultiple01Icon, CursorMagicSelection03Icon, ShoppingBag01Icon, Clock01Icon,
} from "@hugeicons/core-free-icons"

interface Stats {
  totalUsers: number
  totalMessages: number
  totalLinkViews: number
  totalOrders: number
  totalRevenue: number
  dailyMessages: { date: string; count: number }[]
  dailyUsers: { date: string; count: number }[]
  dailyLinkViews: { date: string; count: number }[]
  timeSaved: number
}

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08 } }),
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then(setStats)
      .finally(() => setLoading(false))
  }, [])

  const cards = stats
    ? [
        { label: "کاربران کل", value: stats.totalUsers, icon: UserMultiple02Icon },
        { label: "پیام‌های کل", value: stats.totalMessages, icon: MessageMultiple01Icon },
        { label: "نمایش لینک خرید", value: stats.totalLinkViews, icon: CursorMagicSelection03Icon },
        { label: "سفارشات", value: stats.totalOrders, icon: ShoppingBag01Icon },
        { label: "زمان صرفه‌جویی (دقیقه)", value: stats.timeSaved, icon: Clock01Icon },
      ]
    : []

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold">آمار</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {loading
          ? Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))
          : cards.map((c, i) => (
              <motion.div key={c.label} custom={i} variants={cardVariants} initial="hidden" animate="visible">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-1">
                    <CardTitle className="text-xs text-muted-foreground">{c.label}</CardTitle>
                    <HugeiconsIcon icon={c.icon} className="size-4 text-primary" />
                  </CardHeader>
                  <CardContent>
                    <p className="text-2xl font-bold">{c.value.toLocaleString("fa-IR")}</p>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
      </div>

      {/* Charts */}
      {loading ? (
        <div className="grid sm:grid-cols-2 gap-4">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : !stats || stats.totalMessages === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-2">
          <HugeiconsIcon icon={MessageMultiple01Icon} className="size-12 opacity-30" />
          <p>برای مشاهده آمار ابتدا دستیار را فعال کنید</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">پیام‌ها (۳۰ روز اخیر)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={stats.dailyMessages}>
                    <defs>
                      <linearGradient id="msgGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Area type="monotone" dataKey="count" stroke="hsl(var(--primary))" fill="url(#msgGrad)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">کاربران جدید (۳۰ روز اخیر)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={stats.dailyUsers}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </motion.div>
        </div>
      )}
    </div>
  )
}

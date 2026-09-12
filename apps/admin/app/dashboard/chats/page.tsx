"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { HugeiconsIcon } from "@hugeicons/react"
import { MessageMultiple01Icon } from "@hugeicons/core-free-icons"
import { cn } from "@/lib/utils"

interface Conversation {
  id: string
  mode: string
  startedAt: string
  endUser: { firstName: string | null; username: string | null }
  _count: { messages: number }
}

interface Message {
  id: string
  role: string
  content: string
  createdAt: string
}

export default function ChatsPage() {
  const [convs, setConvs] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [msgLoading, setMsgLoading] = useState(false)

  useEffect(() => {
    fetch("/api/chats")
      .then((r) => r.json())
      .then(setConvs)
      .finally(() => setLoading(false))
  }, [])

  async function openChat(id: string) {
    setSelected(id)
    setMsgLoading(true)
    const data = await fetch(`/api/chats/${id}`).then((r) => r.json())
    setMessages(data)
    setMsgLoading(false)
  }

  return (
    <div className="flex flex-col gap-4">
      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : convs.length === 0 ? (
        <div className="py-20 flex flex-col items-center gap-3 text-muted-foreground">
          <HugeiconsIcon icon={MessageMultiple01Icon} className="size-12 opacity-30" />
          <p>هنوز گفت‌وگویی وجود ندارد</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {convs.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <Card className="cursor-pointer hover:border-primary/50 transition-colors" onClick={() => openChat(c.id)}>
                <CardContent className="flex items-center justify-between gap-4 p-4">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">
                        {c.endUser.firstName ?? c.endUser.username ?? "کاربر ناشناس"}
                      </span>
                      <Badge variant="secondary" className="text-xs">
                        {c.mode === "explore" ? "مشاوره" : "محصول"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {new Date(c.startedAt).toLocaleDateString("fa-IR")} — {c._count.messages.toLocaleString("fa-IR")} پیام
                    </p>
                  </div>
                  <HugeiconsIcon icon={MessageMultiple01Icon} className="size-4 text-muted-foreground" />
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent dir="rtl" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>گفت‌وگو</DialogTitle>
          </DialogHeader>
          <ScrollArea className="h-96" dir="rtl">
            {msgLoading ? (
              <div className="flex flex-col gap-2 p-2">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
              </div>
            ) : (
              <div className="flex flex-col gap-3 p-2">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={cn("flex", m.role === "user" ? "justify-start" : "justify-end")}
                  >
                    <div
                      className={cn(
                        "max-w-[75%] rounded-2xl px-4 py-2 text-sm",
                        m.role === "user"
                          ? "bg-muted text-foreground rounded-tr-sm"
                          : "bg-primary text-primary-foreground rounded-tl-sm"
                      )}
                    >
                      {m.content}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}

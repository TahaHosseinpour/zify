"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  SentIcon,
  RefreshIcon,
  TestTube01Icon,
} from "@hugeicons/core-free-icons"
import { cn } from "@/lib/utils"
import { StatePanel, type DebugState } from "./StatePanel"

interface Turn {
  input: string
  reply: string
  debug: DebugState | null
  products: {
    id: string
    name: string | null
    price: number | null
    imageUrl: string | null
    productUrl: string | null
  }[]
  purchaseUrl: string | null
  showBuyActions: boolean
}

const newSessionId = () => Math.random().toString(36).slice(2, 10)

export default function PlaygroundPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  // The agent's mode/product are part of its state, and /chat overwrites them
  // with whatever the caller sends. Re-sending "explore"/null every turn wiped
  // every pin the agent made, so product mode could never be reproduced here —
  // the Telegram bot keeps the same pair on the conversation row.
  const [mode, setMode] = useState<"explore" | "product">("explore")
  const [productId, setProductId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Generated on the client so a reload always starts a clean thread; the
  // agent keys its memory off it, so nothing leaks between test runs.
  useEffect(() => setSessionId(newSessionId()), [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [turns, sending])

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || sending || !sessionId) return

    setDraft("")
    setSending(true)
    try {
      const res = await fetch("/api/playground/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, sessionId, mode, productId }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.error ?? "خطا")

      setMode(data.mode === "product" ? "product" : "explore")
      setProductId(data.productId ?? null)

      setTurns((prev) => [
        ...prev,
        {
          input: message,
          reply: data.reply ?? "",
          debug: data.debug ?? null,
          products: data.products ?? [],
          purchaseUrl: data.purchaseUrl ?? null,
          showBuyActions: data.showBuyActions !== false,
        },
      ])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ارسال پیام")
      setDraft(message)
    } finally {
      setSending(false)
    }
  }

  function reset() {
    setSessionId(newSessionId())
    setTurns([])
    setDraft("")
    setMode("explore")
    setProductId(null)
    toast.success("گفت‌وگوی جدید شروع شد")
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">
            مثل یک مشتری با دستیار حرف بزنید. زیر هر پاسخ، وضعیت داخلی دستیار برای همان
            نوبت نمایش داده می‌شود.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={reset} disabled={sending}>
          <HugeiconsIcon icon={RefreshIcon} className="size-4" />
          گفت‌وگوی جدید
        </Button>
      </div>

      <div className="flex flex-col gap-6 pb-4">
        {turns.length === 0 && !sending && (
          <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
            <HugeiconsIcon icon={TestTube01Icon} className="size-12 opacity-30" />
            <p className="text-sm">یک پیام بفرستید تا گفت‌وگو شروع شود</p>
          </div>
        )}

        {turns.map((turn, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-2"
          >
            <div className="flex justify-start">
              <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-muted px-4 py-2 text-sm">
                {turn.input}
              </div>
            </div>

            <div className="flex justify-end">
              <div className="max-w-[75%] rounded-2xl rounded-tl-sm bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
                {turn.reply || "—"}
              </div>
            </div>

            {/* Mirrors what the Telegram bot renders — the top-level buy button,
                then one card per product — so a test here predicts production. */}
            {turn.showBuyActions && turn.purchaseUrl && (
              <div className="flex justify-end">
                <a
                  href={turn.purchaseUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg bg-primary px-3 py-1.5 text-[11px] font-medium text-primary-foreground"
                >
                  🛒 خرید محصول
                </a>
              </div>
            )}

            {turn.products.length > 0 && (
              <div className="flex flex-wrap justify-end gap-1.5">
                {turn.products.map((p) => (
                  <div
                    key={p.id}
                    className="flex w-40 flex-col gap-1 rounded-lg border bg-background p-1.5 text-[11px]"
                  >
                    {p.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={p.imageUrl}
                        alt={p.name ?? ""}
                        className="h-20 w-full rounded object-cover"
                      />
                    ) : (
                      <div className="flex h-20 w-full items-center justify-center rounded bg-muted text-[10px] text-muted-foreground">
                        بدون تصویر
                      </div>
                    )}
                    <span className="truncate">{p.name ?? "—"}</span>
                    {p.price != null && (
                      <span className="text-muted-foreground">
                        {p.price.toLocaleString("fa-IR")} تومان
                      </span>
                    )}
                    {turn.showBuyActions && p.productUrl && (
                      <a
                        href={p.productUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded bg-muted px-1.5 py-1 text-center text-[10px]"
                      >
                        🛒 مشاهده و خرید
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}

            {turn.debug && (
              <StatePanel
                debug={turn.debug}
                prev={turns[i - 1]?.debug ?? null}
                turn={i + 1}
              />
            )}
          </motion.div>
        ))}

        {sending && (
          <div className="flex flex-col gap-2">
            <div className="flex justify-end">
              <Skeleton className="h-10 w-48 rounded-2xl" />
            </div>
            <Skeleton className="h-16 rounded-xl" />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={send}
        className="sticky bottom-0 flex items-center gap-2 border-t bg-background py-3"
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="پیام مشتری را بنویسید..."
          disabled={sending || !sessionId}
          className={cn("flex-1")}
        />
        <Button type="submit" disabled={sending || !draft.trim() || !sessionId}>
          <HugeiconsIcon icon={SentIcon} className="size-4" />
          {sending ? "در حال پاسخ..." : "ارسال"}
        </Button>
      </form>
    </div>
  )
}

"use client"

import { useCallback, useState } from "react"
import { createSseStreamParser } from "@/lib/sse"
import type { DebugState } from "./StatePanel"

export interface PlaygroundProduct {
  id: string
  name: string | null
  price: number | null
  imageUrl: string | null
  productUrl: string | null
}

export interface PlaygroundMessage {
  role: "user" | "assistant"
  content: string
  // Only ever set on an assistant turn, and only for turns sent live in this
  // session - a resumed conversation's history comes back from Postgres as
  // plain role/content rows (see api/playground/resume), so its past turns
  // have none of this. Full per-turn tracing still lives in Langfuse.
  debug?: DebugState | null
  products?: PlaygroundProduct[]
  purchaseUrl?: string | null
  showBuyActions?: boolean
}

interface ChatDoneEvent {
  mode?: string
  productId?: string | null
  products?: PlaygroundProduct[]
  purchaseUrl?: string | null
  showBuyActions?: boolean
  debug?: DebugState
}

/** Drives آزمایشگاه فروش (admin's sales playground): same SSE-streaming
 * approach as components/shop-chat/use-chat-stream.ts (POST + reader, since
 * EventSource can't send a body), pointed at /api/playground/stream instead
 * of the public /api/shop-chat. The one real difference is *where* the
 * "done" event's extras land - the storefront only ever shows the latest
 * turn's products, so it keeps a single `lastResult`; the playground shows
 * debug state and product cards under *every* turn, so they're attached to
 * that turn's own message object instead. */
export function usePlaygroundChat() {
  const [messages, setMessages] = useState<PlaygroundMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [mode, setMode] = useState<"explore" | "product">("explore")
  const [productId, setProductId] = useState<string | null>(null)

  const send = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }])
      setIsStreaming(true)

      try {
        const res = await fetch("/api/playground/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, mode, productId }),
        })

        if (!res.ok || !res.body) throw new Error(`playground stream responded ${res.status}`)

        const returnedConversationId = res.headers.get("X-Conversation-Id")
        if (returnedConversationId) setConversationId(returnedConversationId)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        const parser = createSseStreamParser()

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break

          const events = parser.push(decoder.decode(value, { stream: true }))
          for (const evt of events) {
            if (evt.event === "answer") {
              const chunk = (evt.data as { text?: string })?.text ?? ""
              setMessages((prev) => {
                const next = [...prev]
                const lastIdx = next.length - 1
                next[lastIdx] = { ...next[lastIdx], content: next[lastIdx].content + chunk }
                return next
              })
            } else if (evt.event === "done") {
              const data = evt.data as ChatDoneEvent
              if (data.mode === "product" || data.mode === "explore") setMode(data.mode)
              setProductId(data.productId ?? null)
              setMessages((prev) => {
                const next = [...prev]
                const lastIdx = next.length - 1
                next[lastIdx] = {
                  ...next[lastIdx],
                  debug: data.debug ?? null,
                  products: data.products ?? [],
                  purchaseUrl: data.purchaseUrl ?? null,
                  showBuyActions: data.showBuyActions !== false,
                }
                return next
              })
            } else if (evt.event === "error") {
              setMessages((prev) => {
                const next = [...prev]
                const lastIdx = next.length - 1
                next[lastIdx] = {
                  ...next[lastIdx],
                  content: next[lastIdx].content || "متأسفانه در این لحظه مشکلی پیش آمده.",
                }
                return next
              })
            }
          }
        }
      } catch (err) {
        console.error("[playground] stream failed:", err)
        setMessages((prev) => {
          const next = [...prev]
          const lastIdx = next.length - 1
          if (lastIdx >= 0 && next[lastIdx].role === "assistant" && !next[lastIdx].content) {
            next[lastIdx] = { ...next[lastIdx], content: "متأسفانه در این لحظه مشکلی پیش آمده." }
          }
          return next
        })
      } finally {
        setIsStreaming(false)
      }
    },
    [mode, productId],
  )

  const startFresh = useCallback((newConversationId: string) => {
    setMessages([])
    setConversationId(newConversationId)
    setMode("explore")
    setProductId(null)
  }, [])

  /** Resume: replace local state with an old conversation's persisted
   * history and its last known mode/product pin, so the next message
   * continues correctly instead of silently falling back to explore mode. */
  const loadConversation = useCallback(
    (id: string, history: PlaygroundMessage[], resumedMode?: string, resumedProductId?: string | null) => {
      setMessages(history)
      setConversationId(id)
      setMode(resumedMode === "product" ? "product" : "explore")
      setProductId(resumedProductId ?? null)
    },
    [],
  )

  return { messages, isStreaming, conversationId, send, startFresh, loadConversation }
}

"use client"

import { useCallback, useRef, useState } from "react"
import { createSseStreamParser } from "@/lib/sse"
import type { ChatMessage } from "./message-bubble"

export interface StreamProduct {
  id: string
  name: string | null
  price: number | null
  imageUrl: string | null
  productUrl: string | null
}

interface ChatDoneEvent {
  mode?: string
  productId?: string | null
  stage?: string | null
  intent?: string | null
  suggestedProductIds?: string[]
  products?: StreamProduct[]
  purchaseUrl?: string | null
  showBuyActions?: boolean
}

interface UseChatStreamOptions {
  slug: string
  webVisitorId: string
}

/** Drives the storefront chat: posts to /api/shop-chat, reads the SSE
 * response as it arrives (fetch + reader, same approach oostaai's own
 * chat hook uses - EventSource can't send a POST body), and reveals the
 * assistant reply token-by-token into the last message in `messages`. */
export function useChatStream({ slug, webVisitorId }: UseChatStreamOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [lastResult, setLastResult] = useState<ChatDoneEvent | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const modeRef = useRef<"explore" | "product">("explore")
  const productIdRef = useRef<string | null>(null)

  const send = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }])
      setIsStreaming(true)

      try {
        const res = await fetch("/api/shop-chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            slug,
            webVisitorId,
            message: text,
            mode: modeRef.current,
            productId: productIdRef.current,
          }),
        })

        if (!res.ok || !res.body) {
          throw new Error(`shop-chat responded ${res.status}`)
        }

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
              setLastResult(data)
              if (data.mode === "product" || data.mode === "explore") modeRef.current = data.mode
              productIdRef.current = data.productId ?? null
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
        console.error("[shop-chat] stream failed:", err)
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
    [slug, webVisitorId],
  )

  /** New chat: local state only - the server-side conversation row is
   * created by POST /api/shop-chat/new, which callers hit first and pass the
   * resulting id here. */
  const startFresh = useCallback((newConversationId: string) => {
    setMessages([])
    setLastResult(null)
    setConversationId(newConversationId)
    modeRef.current = "explore"
    productIdRef.current = null
  }, [])

  /** Resume: replace local state with an old conversation's history (from
   * POST /api/shop-chat/resume) and continue it from here. */
  const loadConversation = useCallback((id: string, history: ChatMessage[]) => {
    setMessages(history)
    setLastResult(null)
    setConversationId(id)
    modeRef.current = "explore"
    productIdRef.current = null
  }, [])

  return { messages, isStreaming, lastResult, conversationId, send, startFresh, loadConversation }
}

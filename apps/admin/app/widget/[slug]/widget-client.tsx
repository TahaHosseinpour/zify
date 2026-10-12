"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Cancel01Icon } from "@hugeicons/core-free-icons"
import { ChatInput } from "@/components/shop-chat/chat-input"
import { MessageBubble } from "@/components/shop-chat/message-bubble"
import { ProductCard } from "@/components/shop-chat/product-card"
import { useChatStream } from "@/components/shop-chat/use-chat-stream"
import { getOrCreateVisitorId } from "@/lib/shop-visitor-id"

const STARTER_PROMPTS = ["چه محصولاتی دارید؟", "یه پیشنهاد خوب می‌خوام", "ارزون‌ترین‌ها رو نشونم بده"]

/** The storefront chat sized for a small frame: one column, no history
 * sidebar, product cards two to a row. Talks to the same /api/shop-chat. */
export function WidgetChatClient({
  slug,
  shopName,
  welcomeMessage,
}: {
  slug: string
  shopName: string
  welcomeMessage?: string | null
}) {
  const [webVisitorId] = useState(() => getOrCreateVisitorId())
  const scrollRef = useRef<HTMLDivElement>(null)

  const { messages, isStreaming, lastResult, send, startFresh } = useChatStream({ slug, webVisitorId })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, lastResult])

  async function handleNewChat() {
    const res = await fetch("/api/shop-chat/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, webVisitorId }),
    })
    const data = await res.json()
    if (data.conversationId) startFresh(data.conversationId)
  }

  const products = lastResult?.products ?? []
  const showProducts = products.length > 0 && !isStreaming
  const lastMessage = messages[messages.length - 1]
  const isThinking = isStreaming && lastMessage?.role === "assistant" && lastMessage.content === ""
  const disabled = isStreaming || !webVisitorId

  return (
    <div className="flex h-dvh flex-col bg-background" dir="rtl">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-secondary px-3">
        <span className="truncate text-sm font-medium">{shopName}</span>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={handleNewChat} disabled={isStreaming}>
              <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
              چت جدید
            </Button>
          )}
          {/* On a phone the open chat covers the launcher, so closing has to
           * be asked for from in here (widget.js listens for this). */}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="بستن"
            onClick={() => window.parent.postMessage("zify-widget:close", "*")}
          >
            <HugeiconsIcon icon={Cancel01Icon} />
          </Button>
        </div>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="whitespace-pre-line text-base font-semibold text-muted-foreground">
              {welcomeMessage || "بنویس دنبال چی هستی کمکت کنم؟"}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {STARTER_PROMPTS.map((prompt) => (
                <Button
                  key={prompt}
                  variant="outline"
                  size="sm"
                  className="rounded-full"
                  onClick={() => send(prompt)}
                  disabled={disabled}
                >
                  {prompt}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col">
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} isThinking={isThinking && i === messages.length - 1} />
            ))}
            {showProducts && (
              <div className="grid grid-cols-2 gap-2 pt-3">
                {products.map((p) => (
                  <ProductCard
                    key={p.id}
                    product={{ id: p.id, name: p.name ?? "", price: p.price, imageUrl: p.imageUrl, productUrl: p.productUrl }}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-border p-2">
        <ChatInput onSend={send} disabled={disabled} />
      </div>
    </div>
  )
}

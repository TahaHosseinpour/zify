"use client"

import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Clock01Icon, TestTube01Icon } from "@hugeicons/core-free-icons"
import { ChatInput } from "@/components/shop-chat/chat-input"
import { MessageBubble } from "@/components/shop-chat/message-bubble"
import { ProductCard } from "@/components/shop-chat/product-card"
import { StatePanel } from "./StatePanel"
import { PlaygroundHistorySheet } from "./history-sheet"
import { usePlaygroundChat } from "./use-playground-chat"

const STARTER_PROMPTS = [
  "چه محصولاتی دارید؟",
  "دنبال یه پیشنهاد خوب می‌گردم",
  "ارزون‌ترین‌ها رو نشونم بده",
  "می‌خوام هدیه بخرم",
]

/** آزمایشگاه فروش: the same chat components/streaming UX the real storefront
 * uses (see app/shops/[slug]/chat/chat-client.tsx), pointed at the admin's
 * own authenticated /api/playground/* routes instead of the public
 * /api/shop-chat ones. Two things stay on top of the storefront's own
 * feature set: a debug snapshot under every assistant turn (see
 * use-playground-chat.ts + StatePanel - full tracing still lives in
 * Langfuse, same run) and a "چت‌های قبلی" history sheet, since a shop owner
 * testing their bot has the same "what did I try last time" need a real
 * customer resuming a chat does. */
export default function PlaygroundPage() {
  const { messages, isStreaming, conversationId, send, startFresh, loadConversation } = usePlaygroundChat()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  async function handleNewChat() {
    const res = await fetch("/api/playground/new", { method: "POST" })
    const data = await res.json()
    if (data.conversationId) {
      startFresh(data.conversationId)
      setHistoryRefreshKey((k) => k + 1)
    }
  }

  async function handleResume(id: string) {
    const res = await fetch("/api/playground/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversationId: id }),
    })
    const data = await res.json()
    if (!res.ok) {
      toast.error(data?.error ?? "خطا در بازیابی گفتگو")
      return
    }
    if (data.conversationId) loadConversation(data.conversationId, data.messages ?? [], data.mode, data.productId)
  }

  async function handleSend(text: string) {
    await send(text)
    setHistoryRefreshKey((k) => k + 1)
  }

  const lastMessage = messages[messages.length - 1]
  const isThinking = isStreaming && lastMessage?.role === "assistant" && lastMessage.content === ""

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          مثل یک مشتری با دستیار حرف بزنید — دقیقاً همان تجربه‌ای که مشتری در فروشگاه شما می‌بیند.
        </p>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setHistoryOpen(true)}>
            <HugeiconsIcon icon={Clock01Icon} className="size-4" />
            چت‌های قبلی
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleNewChat} disabled={isStreaming}>
            <HugeiconsIcon icon={Add01Icon} className="size-4" />
            چت جدید
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1 rounded-xl border bg-background">
        {messages.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 px-4">
            <div className="flex flex-col items-center gap-2 text-center">
              <HugeiconsIcon icon={TestTube01Icon} className="size-10 text-muted-foreground/40" />
              <h2 className="text-base font-medium text-muted-foreground">
                یک پیام بفرستید تا گفت‌وگو شروع شود
              </h2>
            </div>

            <ChatInput onSend={handleSend} className="w-full max-w-xl" autoFocus />

            <div className="flex w-full max-w-xl flex-wrap justify-center gap-2">
              {STARTER_PROMPTS.map((prompt) => (
                <Button
                  key={prompt}
                  variant="outline"
                  size="sm"
                  className="rounded-full"
                  onClick={() => handleSend(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="absolute inset-0 overflow-y-auto px-4 pb-32 pt-6">
              <div className="mx-auto flex max-w-2xl flex-col">
                {messages.map((m, i) => {
                  const isLast = i === messages.length - 1
                  const products = m.products ?? []
                  // Most recent *prior* assistant turn's debug, so StatePanel
                  // can highlight what this turn actually moved.
                  const prevDebug = [...messages.slice(0, i)].reverse().find((x) => x.role === "assistant")?.debug

                  return (
                    <div key={i} className="flex flex-col gap-3">
                      <MessageBubble message={m} isThinking={isThinking && isLast} />

                      {m.role === "assistant" && m.showBuyActions && m.purchaseUrl && (
                        <a
                          href={m.purchaseUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="self-start rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
                        >
                          🛒 خرید محصول
                        </a>
                      )}

                      {m.role === "assistant" && products.length > 0 && (
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                          {products.map((p) => (
                            <ProductCard
                              key={p.id}
                              product={{
                                id: p.id,
                                name: p.name ?? "",
                                price: p.price,
                                imageUrl: p.imageUrl,
                                productUrl: m.showBuyActions ? p.productUrl : null,
                              }}
                            />
                          ))}
                        </div>
                      )}

                      {m.role === "assistant" && m.debug && (
                        <StatePanel debug={m.debug} prev={prevDebug ?? null} turn={Math.ceil((i + 1) / 2)} />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/95 to-transparent px-4 pb-4 pt-8">
              <ChatInput onSend={handleSend} disabled={isStreaming} className="mx-auto max-w-2xl" />
            </div>
          </>
        )}
      </div>

      <PlaygroundHistorySheet
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        activeConversationId={conversationId}
        onResume={handleResume}
        refreshKey={historyRefreshKey}
      />
    </div>
  )
}

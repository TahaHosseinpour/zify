"use client"

import { useEffect, useRef, useState } from "react"
import { SidebarProvider, SidebarInset, SidebarTrigger, useSidebar } from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Clock01Icon, ChartIcon } from "@hugeicons/core-free-icons"
import { ChatInput } from "@/components/shop-chat/chat-input"
import { MessageBubble } from "@/components/shop-chat/message-bubble"
import { ProductCard } from "@/components/shop-chat/product-card"
import { ChatHistorySidebar } from "@/components/shop-chat/chat-history-sidebar"
import { UsageSheet } from "@/components/shop-chat/usage-sheet"
import { useChatStream } from "@/components/shop-chat/use-chat-stream"
import { getOrCreateVisitorId } from "@/lib/shop-visitor-id"

const STARTER_PROMPTS = [
  "چه محصولاتی دارید؟",
  "دنبال یه پیشنهاد خوب می‌گردم",
  "ارزون‌ترین‌ها رو نشونم بده",
  "می‌خوام هدیه بخرم",
]

/** Lives inside SidebarInset (a descendant of SidebarProvider), which is
 * what lets it call useSidebar() to actually open the history sidebar -
 * ShopChatClient itself renders SidebarProvider, so it's one level too high
 * in the tree to consume that context directly.
 *
 * Modeled on oostaai's ThreadNavBar: a thin `bg-secondary` strip with the
 * title, not a tall bordered header - actions collapse to icon-only ghost
 * buttons with tooltips instead of labeled outline pills. */
function ChatTopBar({
  shopName,
  onNewChat,
  onUsage,
}: {
  shopName: string
  onNewChat: () => void
  onUsage: () => void
}) {
  const { toggleSidebar } = useSidebar()
  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-secondary px-3">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="size-7" />
        <span className="text-sm font-medium">{shopName}</span>
      </div>
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onNewChat} aria-label="چت جدید">
              <HugeiconsIcon icon={Add01Icon} className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>چت جدید</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={toggleSidebar} aria-label="چت‌های قبلی">
              <HugeiconsIcon icon={Clock01Icon} className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>چت‌های قبلی</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onUsage} aria-label="سقف مصرف">
              <HugeiconsIcon icon={ChartIcon} className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>سقف مصرف</TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}

export function ShopChatClient({ slug, shopName, initialMessage }: {
  slug: string
  shopName: string
  initialMessage: string
}) {
  const [webVisitorId] = useState(() => getOrCreateVisitorId())
  const [usageOpen, setUsageOpen] = useState(false)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sentInitialMessage = useRef(false)

  const { messages, isStreaming, lastResult, conversationId, send, startFresh, loadConversation } =
    useChatStream({ slug, webVisitorId })

  // A new "done" event with a fresh set of suggested products is worth
  // reflecting in the history list's preview text right away. Bumped during
  // render (rather than an effect) by comparing against the previous
  // render's lastResult, per https://react.dev/learn/you-might-not-need-an-effect.
  const [prevLastResult, setPrevLastResult] = useState(lastResult)
  if (lastResult !== prevLastResult) {
    setPrevLastResult(lastResult)
    if (lastResult) setHistoryRefreshKey((k) => k + 1)
  }

  useEffect(() => {
    if (sentInitialMessage.current || !initialMessage) return
    sentInitialMessage.current = true
    send(initialMessage)
  }, [webVisitorId, initialMessage, send])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  async function handleNewChat() {
    const res = await fetch("/api/shop-chat/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, webVisitorId }),
    })
    const data = await res.json()
    if (data.conversationId) startFresh(data.conversationId)
  }

  async function handleResume(id: string) {
    const res = await fetch("/api/shop-chat/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, webVisitorId, conversationId: id }),
    })
    const data = await res.json()
    if (data.conversationId) loadConversation(data.conversationId, data.messages ?? [])
  }

  const products = lastResult?.products ?? []
  const showProducts = products.length > 0 && !isStreaming
  const lastMessage = messages[messages.length - 1]
  const isThinking = isStreaming && lastMessage?.role === "assistant" && lastMessage.content === ""

  return (
    <SidebarProvider defaultOpen={false}>
      <ChatHistorySidebar
        slug={slug}
        webVisitorId={webVisitorId}
        activeConversationId={conversationId}
        onResume={handleResume}
        refreshKey={historyRefreshKey}
      />
      <SidebarInset className="bg-background">
        <ChatTopBar shopName={shopName} onNewChat={handleNewChat} onUsage={() => setUsageOpen(true)} />

        {/* Mirrors oostaai's ChatPageLayout + chat-input/input.tsx: the
         * composer isn't a permanent footer bar. Before the first message
         * it sits centered in the empty viewport with the greeting and
         * starter prompts (their `absolute inset-0 items-center justify-center`
         * case); once a thread exists, it drops to a floating bar over a
         * fade-to-background gradient at the bottom of the scrolling thread
         * (their `absolute bottom-0` case) instead of staying put. */}
        <div className="relative min-h-0 flex-1">
          {messages.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 px-4">
              <div className="flex flex-col items-center gap-1 text-center">
                <h2 className="bg-gradient-to-r from-muted-foreground via-muted-foreground/70 to-muted-foreground/40 bg-clip-text text-2xl font-semibold text-transparent">
                  بنویس دنبال چی هستی کمکت کنم؟
                </h2>
              </div>

              <ChatInput onSend={send} disabled={isStreaming || !webVisitorId} className="w-full max-w-2xl" />

              <div className="flex w-full max-w-2xl flex-wrap justify-center gap-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <Button
                    key={prompt}
                    variant="outline"
                    size="sm"
                    className="rounded-full"
                    onClick={() => send(prompt)}
                    disabled={isStreaming || !webVisitorId}
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
                  {messages.map((m, i) => (
                    <MessageBubble key={i} message={m} isThinking={isThinking && i === messages.length - 1} />
                  ))}

                  {showProducts && (
                    <div className="grid grid-cols-2 gap-3 pt-4 sm:grid-cols-3">
                      {products.map((p) => (
                        <ProductCard
                          key={p.id}
                          product={{ id: p.id, name: p.name ?? "", price: p.price, imageUrl: p.imageUrl, productUrl: p.productUrl }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/95 to-transparent px-4 pb-4 pt-8">
                <ChatInput
                  onSend={send}
                  disabled={isStreaming || !webVisitorId}
                  className="mx-auto max-w-2xl"
                />
              </div>
            </>
          )}
        </div>
      </SidebarInset>

      <UsageSheet slug={slug} webVisitorId={webVisitorId} open={usageOpen} onOpenChange={setUsageOpen} />
    </SidebarProvider>
  )
}

"use client"

import { useEffect, useRef, useState } from "react"
import { SidebarProvider, SidebarInset, SidebarTrigger, useSidebar } from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Clock01Icon, ChartIcon } from "@hugeicons/core-free-icons"
import { ChatInput } from "@/components/shop-chat/chat-input"
import { MessageBubble } from "@/components/shop-chat/message-bubble"
import { ProductCard } from "@/components/shop-chat/product-card"
import { ChatHistorySidebar } from "@/components/shop-chat/chat-history-sidebar"
import { UsageSheet } from "@/components/shop-chat/usage-sheet"
import { useChatStream } from "@/components/shop-chat/use-chat-stream"
import { getOrCreateVisitorId } from "@/lib/shop-visitor-id"

/** Lives inside SidebarInset (a descendant of SidebarProvider), which is
 * what lets it call useSidebar() to actually open the history sidebar -
 * ShopChatClient itself renders SidebarProvider, so it's one level too high
 * in the tree to consume that context directly. */
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
    <header className="flex h-14 items-center justify-between border-b border-border px-4">
      <div className="flex items-center gap-2">
        <SidebarTrigger />
        <span className="text-sm font-medium">{shopName}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="gap-1.5 rounded-full" onClick={onNewChat}>
          <HugeiconsIcon icon={Add01Icon} className="size-4" />
          چت جدید
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5 rounded-full" onClick={toggleSidebar}>
          <HugeiconsIcon icon={Clock01Icon} className="size-4" />
          چت‌های قبلی
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5 rounded-full" onClick={onUsage}>
          <HugeiconsIcon icon={ChartIcon} className="size-4" />
          سقف مصرف
        </Button>
      </div>
    </header>
  )
}

export function ShopChatClient({ slug, shopName, initialMessage }: {
  slug: string
  shopName: string
  initialMessage: string
}) {
  const [webVisitorId, setWebVisitorId] = useState("")
  const [usageOpen, setUsageOpen] = useState(false)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sentInitialMessage = useRef(false)

  const { messages, isStreaming, lastResult, conversationId, send, startFresh, loadConversation } =
    useChatStream({ slug, webVisitorId })

  useEffect(() => {
    setWebVisitorId(getOrCreateVisitorId())
  }, [])

  useEffect(() => {
    if (!webVisitorId || sentInitialMessage.current || !initialMessage) return
    sentInitialMessage.current = true
    send(initialMessage)
  }, [webVisitorId, initialMessage, send])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  // A new "done" event with a fresh set of suggested products is worth
  // reflecting in the history list's preview text right away.
  useEffect(() => {
    if (lastResult) setHistoryRefreshKey((k) => k + 1)
  }, [lastResult])

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

  return (
    <SidebarProvider>
      <ChatHistorySidebar
        slug={slug}
        webVisitorId={webVisitorId}
        activeConversationId={conversationId}
        onResume={handleResume}
        refreshKey={historyRefreshKey}
      />
      <SidebarInset className="bg-background">
        <ChatTopBar shopName={shopName} onNewChat={handleNewChat} onUsage={() => setUsageOpen(true)} />

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto flex max-w-2xl flex-col gap-4">
            {messages.length === 0 && (
              <p className="py-16 text-center text-sm text-muted-foreground">
                سلام! چطور می‌تونم کمکتون کنم؟
              </p>
            )}
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} />
            ))}

            {showProducts && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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

        <div className="border-t border-border p-4">
          <ChatInput
            onSend={send}
            disabled={isStreaming || !webVisitorId}
            className="mx-auto max-w-2xl"
          />
        </div>
      </SidebarInset>

      <UsageSheet slug={slug} webVisitorId={webVisitorId} open={usageOpen} onOpenChange={setUsageOpen} />
    </SidebarProvider>
  )
}

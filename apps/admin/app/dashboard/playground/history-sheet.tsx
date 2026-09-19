"use client"

import { useEffect, useState } from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { HugeiconsIcon } from "@hugeicons/react"
import { Comment01Icon } from "@hugeicons/core-free-icons"

interface HistoryEntry {
  id: string
  lastMessageAt: string
  preview: string | null
}

// Same today/this-week/older buckets as components/shop-chat/chat-history-sidebar.tsx.
function bucketLabel(lastMessageAt: string): string {
  const then = new Date(lastMessageAt)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - then.getTime()) / (24 * 60 * 60 * 1000))
  if (diffDays < 1 && then.getDate() === now.getDate()) return "امروز"
  if (diffDays < 7) return "هفته اخیر"
  return "قدیمی‌تر"
}

/** آزمایشگاه فروش's "چت‌های قبلی" list. A Sheet rather than
 * components/shop-chat/chat-history-sidebar.tsx's own Sidebar: this page
 * already lives inside the dashboard's own SidebarProvider, and nesting a
 * second one just to get an offcanvas panel would fight that provider's
 * `min-h-svh` sizing. A Sheet gets the same "click a button, see the list"
 * behaviour without the nested-provider layout risk. */
export function PlaygroundHistorySheet({
  open,
  onOpenChange,
  activeConversationId,
  onResume,
  refreshKey,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  activeConversationId: string | null
  onResume: (conversationId: string) => void
  refreshKey: number
}) {
  const [entries, setEntries] = useState<HistoryEntry[]>([])

  useEffect(() => {
    if (!open) return
    fetch("/api/playground/history")
      .then((r) => r.json())
      .then((data) => Array.isArray(data) && setEntries(data))
      .catch(() => {})
  }, [open, refreshKey])

  const groups = new Map<string, HistoryEntry[]>()
  for (const entry of entries) {
    const label = bucketLabel(entry.lastMessageAt)
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label)!.push(entry)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left">
        <SheetHeader>
          <SheetTitle>چت‌های قبلی</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-4">
          {entries.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">هنوز گفت‌وگویی نداشتید</p>
          ) : (
            Array.from(groups.entries()).map(([label, items]) => (
              <div key={label} className="flex flex-col gap-1">
                <span className="px-1 text-xs font-medium text-muted-foreground">{label}</span>
                <div className="flex flex-col gap-0.5">
                  {items.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => {
                        onResume(entry.id)
                        onOpenChange(false)
                      }}
                      className={
                        "flex items-center gap-2 rounded-lg px-2 py-2 text-start text-sm transition-colors hover:bg-accent " +
                        (entry.id === activeConversationId ? "bg-accent font-medium" : "")
                      }
                    >
                      <HugeiconsIcon icon={Comment01Icon} className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{entry.preview || "گفت‌وگو"}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

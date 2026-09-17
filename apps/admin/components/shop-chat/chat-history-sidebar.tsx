"use client"

import { useEffect, useState } from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { HugeiconsIcon } from "@hugeicons/react"
import { Comment01Icon } from "@hugeicons/core-free-icons"

interface HistoryEntry {
  id: string
  lastMessageAt: string
  preview: string | null
}

// today / this week / older - simple buckets, no extra date library needed.
function bucketLabel(lastMessageAt: string): string {
  const then = new Date(lastMessageAt)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - then.getTime()) / (24 * 60 * 60 * 1000))
  if (diffDays < 1 && then.getDate() === now.getDate()) return "امروز"
  if (diffDays < 7) return "هفته اخیر"
  return "قدیمی‌تر"
}

interface ChatHistorySidebarProps {
  slug: string
  webVisitorId: string
  activeConversationId: string | null
  onResume: (conversationId: string) => void
  refreshKey: number
}

/** Desktop: a real collapsible sidebar (components/ui/sidebar.tsx - the same
 * primitive apps/admin/components/app-sidebar.tsx uses for the dashboard
 * nav). It already collapses into a Sheet-based drawer on mobile on its
 * own, so this one component covers both. */
export function ChatHistorySidebar({
  slug,
  webVisitorId,
  activeConversationId,
  onResume,
  refreshKey,
}: ChatHistorySidebarProps) {
  const [entries, setEntries] = useState<HistoryEntry[]>([])

  useEffect(() => {
    if (!webVisitorId) return
    fetch(`/api/shop-chat/history?slug=${encodeURIComponent(slug)}&webVisitorId=${encodeURIComponent(webVisitorId)}`)
      .then((r) => r.json())
      .then((data) => Array.isArray(data) && setEntries(data))
      .catch(() => {})
  }, [slug, webVisitorId, refreshKey])

  const groups = new Map<string, HistoryEntry[]>()
  for (const entry of entries) {
    const label = bucketLabel(entry.lastMessageAt)
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label)!.push(entry)
  }

  return (
    <Sidebar side="right" collapsible="offcanvas">
      <SidebarContent className="py-3">
        {entries.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">هنوز گفت‌وگویی ندارید</p>
        ) : (
          Array.from(groups.entries()).map(([label, items]) => (
            <SidebarGroup key={label}>
              <SidebarGroupLabel>{label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {items.map((entry) => (
                    <SidebarMenuItem key={entry.id}>
                      <SidebarMenuButton
                        isActive={entry.id === activeConversationId}
                        onClick={() => onResume(entry.id)}
                        className="gap-2"
                      >
                        <HugeiconsIcon icon={Comment01Icon} className="size-4 shrink-0" />
                        <span className="truncate">{entry.preview || "گفت‌وگو"}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))
        )}
      </SidebarContent>
    </Sidebar>
  )
}

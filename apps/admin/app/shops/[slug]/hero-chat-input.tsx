"use client"

import { useRouter } from "next/navigation"
import { ChatInput } from "@/components/shop-chat/chat-input"

/** The hero's chat box doesn't chat by itself - typing and submitting (or,
 * per the brief, just focusing it) hands off to the full chat page. Kept as
 * its own client component so /shops/[slug]/page.tsx can stay a plain
 * Server Component for the rest of the page. */
export function HeroChatInput({ slug }: { slug: string }) {
  const router = useRouter()

  function goToChat(message: string) {
    router.push(`/shops/${slug}/chat${message ? `?m=${encodeURIComponent(message)}` : ""}`)
  }

  return (
    <ChatInput
      onSend={goToChat}
      onFocus={() => goToChat("")}
      placeholder="سلام! دنبال چی می‌گردید؟"
      className="mx-auto max-w-xl"
    />
  )
}

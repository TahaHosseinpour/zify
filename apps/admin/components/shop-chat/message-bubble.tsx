import { cn } from "@/lib/utils"

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

/** Plain-text bubble, not a markdown renderer - the agent's replies are
 * conversational Persian sentences, not formatted documents, so this only
 * needs to preserve line breaks. */
export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"
  return (
    <div className={cn("flex", isUser ? "justify-start" : "justify-end")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-7",
          isUser
            ? "rounded-tl-sm bg-secondary text-secondary-foreground"
            : "rounded-tr-sm bg-primary text-primary-foreground",
        )}
      >
        {message.content}
      </div>
    </div>
  )
}

import { HugeiconsIcon } from "@hugeicons/react"
import { SparklesIcon } from "@hugeicons/core-free-icons"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Components } from "react-markdown"

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

// No @tailwindcss/typography plugin in this app, so the assistant's markdown
// gets its spacing/weight per-element here instead of a "prose" class - kept
// logical (ps-/border-s-) since the whole app renders dir="rtl".
const markdownComponents: Components = {
  p: ({ children }) => <p className="text-sm leading-7 text-foreground [&:not(:first-child)]:mt-2">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="list-disc space-y-1 ps-5 text-sm leading-7">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 ps-5 text-sm leading-7">{children}</ol>,
  li: ({ children }) => <li className="text-foreground">{children}</li>,
  h1: ({ children }) => <h1 className="text-base font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="border-s-2 border-border ps-3 text-muted-foreground">{children}</blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 text-xs" dir="ltr">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs" dir="ltr">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-border px-2 py-1 text-start font-medium">{children}</th>,
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
  hr: () => <hr className="border-border" />,
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="flex w-full flex-col gap-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

/** Modeled on oostaai's thread-item/message pattern: the user's turn is a
 * plain muted pill aligned to the reading end, the assistant's turn has no
 * bubble at all - just a small "پاسخ" label (their "Answer" + book icon,
 * here a sparkle since this is a sales agent, not a search engine) above
 * flowing text. `isThinking` swaps that text for shimmering placeholder
 * bars (oostaai's MotionSkeleton) while the stream hasn't produced its
 * first token yet. */
export function MessageBubble({ message, isThinking }: { message: ChatMessage; isThinking?: boolean }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-start pt-4">
        <div className="max-w-[80%] rounded-lg bg-muted px-3 py-1.5 text-sm leading-7 whitespace-pre-wrap text-foreground">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col items-start gap-2 pt-4">
      <div className="flex flex-row items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <HugeiconsIcon icon={SparklesIcon} className="size-3.5" />
        پاسخ
      </div>
      {isThinking ? (
        <div className="flex w-full flex-col items-start gap-2">
          <div className="h-4 w-full animate-pulse rounded-sm bg-gradient-to-r from-muted-foreground/30 via-muted-foreground/15 to-transparent" />
          <div className="h-4 w-[70%] animate-pulse rounded-sm bg-gradient-to-r from-muted-foreground/30 via-muted-foreground/15 to-transparent" />
          <div className="h-4 w-[50%] animate-pulse rounded-sm bg-gradient-to-r from-muted-foreground/30 via-muted-foreground/15 to-transparent" />
        </div>
      ) : (
        <MarkdownContent content={message.content} />
      )}
    </div>
  )
}

"use client"

import { useState, type KeyboardEvent } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowUp01Icon } from "@hugeicons/core-free-icons"
import { cn } from "@/lib/utils"

interface ChatInputProps {
  onSend: (message: string) => void
  onFocus?: () => void
  disabled?: boolean
  placeholder?: string
  autoFocus?: boolean
  className?: string
}

/** The message composer, shared by the storefront hero (which navigates to
 * the chat page on submit) and the chat page itself (which streams a
 * reply) - both just pass a different `onSend`. Modeled on oostaai's
 * chat-input/input.tsx: a floating rounded card with the editor on top and
 * a thin dashed-border toolbar row underneath (hint text + send button),
 * rather than a single-row textarea-and-button bar. Plain textarea, not a
 * rich editor: this is a sales conversation, not a document. */
export function ChatInput({ onSend, onFocus, disabled, placeholder, autoFocus, className }: ChatInputProps) {
  const [value, setValue] = useState("")
  const hasText = value.trim().length > 0

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue("")
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div
      className={cn(
        "w-full rounded-xl border border-border bg-background shadow-sm",
        "focus-within:ring-2 focus-within:ring-primary/20",
        className,
      )}
    >
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={onFocus}
        placeholder={placeholder ?? "پیامتون رو بنویسید..."}
        autoFocus={autoFocus}
        rows={1}
        disabled={disabled}
        className="min-h-10 resize-none border-0 bg-transparent px-3 pt-3 pb-1 shadow-none focus-visible:ring-0"
      />
      <div className="flex w-full items-center justify-between gap-2 border-t border-dashed border-border px-2 py-2">
        <p className="px-1 text-xs text-muted-foreground">
          {hasText ? "برای خط جدید Shift+Enter" : " "}
        </p>
        <Button
          size="icon"
          className="size-8 shrink-0 rounded-full"
          variant={hasText ? "default" : "secondary"}
          disabled={disabled || !hasText}
          onClick={submit}
          aria-label="ارسال"
        >
          <HugeiconsIcon icon={ArrowUp01Icon} className="size-4" />
        </Button>
      </div>
    </div>
  )
}

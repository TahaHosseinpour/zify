"use client"

import { useState, type KeyboardEvent } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { SentIcon } from "@hugeicons/core-free-icons"
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
 * reply) - both just pass a different `onSend`. Plain textarea, not a rich
 * editor: this is a sales conversation, not a document. */
export function ChatInput({ onSend, onFocus, disabled, placeholder, autoFocus, className }: ChatInputProps) {
  const [value, setValue] = useState("")

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
        "flex items-end gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm",
        "focus-within:ring-2 focus-within:ring-primary/30",
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
        className="min-h-10 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
      />
      <Button
        size="icon"
        className="size-10 shrink-0 rounded-xl"
        disabled={disabled || !value.trim()}
        onClick={submit}
        aria-label="ارسال"
      >
        <HugeiconsIcon icon={SentIcon} className="size-5" />
      </Button>
    </div>
  )
}

"use client"

import * as React from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { ViewIcon, ViewOffSlashIcon } from "@hugeicons/core-free-icons"

import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"

function PasswordInput({ className, ...props }: Omit<React.ComponentProps<"input">, "type">) {
  const [visible, setVisible] = React.useState(false)

  return (
    <div className="relative" dir="ltr">
      <Input type={visible ? "text" : "password"} className={cn("pr-9", className)} {...props} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "پنهان کردن رمز عبور" : "نمایش رمز عبور"}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-md text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <HugeiconsIcon icon={visible ? ViewOffSlashIcon : ViewIcon} size={16} strokeWidth={2} />
      </button>
    </div>
  )
}

export { PasswordInput }

"use client"

import { cn } from "@/lib/utils"

interface ChoiceGroupProps<T extends string | number> {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
  className?: string
  "aria-label"?: string
}

/** A small set of mutually exclusive options shown side by side - for choices
 * with few enough values that seeing them all beats opening a menu (a plan, a
 * billing period). */
export function ChoiceGroup<T extends string | number>({
  value,
  onChange,
  options,
  className,
  ...props
}: ChoiceGroupProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={props["aria-label"]}
      className={cn("inline-flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1", className)}
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
              selected
                ? "bg-background font-semibold text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

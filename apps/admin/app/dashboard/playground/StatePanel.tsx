"use client"

import { useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowDown01Icon, ArrowLeft01Icon } from "@hugeicons/core-free-icons"
import { cn } from "@/lib/utils"
import {
  FILTER_LABELS,
  FILTER_STATUS_LABELS,
  INTENT_LABELS,
  SORT_LABELS,
  MODE_LABELS,
  NODE_LABELS,
  OBJECTION_LABELS,
  STAGE_LABELS,
  TYPE_LABELS,
  VALUE_DRIVER_LABELS,
  label,
} from "./labels"

export interface DebugState {
  path: string[]
  intent: string | null
  mode: string | null
  stage: string | null
  valueDriver: string | null
  objection: string | null
  productId: string | null
  exploreFilters: Record<string, string | number>
  filterStatus: string | null
  filterEffective: Record<string, string | number>
  filtersDropped: string[]
  outOfCatalog: boolean
  sort: string | null
  candidateCount: number
  excludedProductIds: string[]
  shownProducts: { id: string; name: string | null }[]
  retrieved: {
    rawCount: number
    contextCount: number
    byType: Record<string, number>
    scores: number[]
  }
  messageCount: number
  hasSummary: boolean
  summaryChars: number
  latencyMs: number
}

const fa = (n: number) => n.toLocaleString("fa-IR")

/** One state feature: label on the right, value chip on the left. */
function Field({
  name,
  value,
  changed,
  tone = "neutral",
}: {
  name: string
  value: string | null
  changed?: boolean
  tone?: "neutral" | "key" | "warn"
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <span className="text-[11px] text-muted-foreground">{name}</span>
      <span
        className={cn(
          "rounded-md px-1.5 py-0.5 text-[11px] font-medium",
          value === null && "text-muted-foreground/50",
          value !== null && tone === "neutral" && "bg-muted text-foreground",
          value !== null && tone === "key" && "bg-primary/10 text-primary",
          value !== null && tone === "warn" && "bg-destructive/10 text-destructive",
          changed && "ring-1 ring-primary/40",
        )}
      >
        {value ?? "—"}
      </span>
    </div>
  )
}

/** Filter predicates as key: value chips, or an em-dash when there are none. */
function Chips({ entries }: { entries: [string, string | number][] }) {
  if (entries.length === 0)
    return <span className="text-[11px] text-muted-foreground/50">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="rounded-md bg-background px-1.5 py-0.5 text-[11px] ring-1 ring-border"
        >
          <span className="text-muted-foreground">{FILTER_LABELS[k] ?? k}: </span>
          {typeof v === "number" ? fa(v) : String(v)}
        </span>
      ))}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-t border-dashed pt-2">
      <span className="text-[10px] font-semibold text-muted-foreground/70">{title}</span>
      {children}
    </div>
  )
}

export function StatePanel({
  debug,
  prev,
  turn,
}: {
  debug: DebugState
  prev?: DebugState | null
  turn: number
}) {
  const [open, setOpen] = useState(true)

  // Highlight what this turn actually moved, so a long transcript is scannable.
  const changed = (key: keyof DebugState) =>
    Boolean(prev) && JSON.stringify(prev?.[key]) !== JSON.stringify(debug[key])

  const filters = Object.entries(debug.exploreFilters ?? {})
  const effective = Object.entries(debug.filterEffective ?? {})
  const types = Object.entries(debug.retrieved?.byType ?? {})

  return (
    <div dir="rtl" className="rounded-xl border border-dashed bg-muted/30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-right"
      >
        <HugeiconsIcon
          icon={open ? ArrowDown01Icon : ArrowLeft01Icon}
          className="size-3.5 shrink-0 text-muted-foreground"
        />
        <span className="text-[11px] font-semibold">وضعیت گفت‌وگو</span>
        <span className="text-[10px] text-muted-foreground">نوبت {fa(turn)}</span>
        <span className="ms-auto flex items-center gap-1.5">
          {debug.intent && (
            <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
              {label(INTENT_LABELS, debug.intent)}
            </span>
          )}
          <span className="font-mono text-[10px] text-muted-foreground" dir="ltr">
            {fa(debug.latencyMs)}ms
          </span>
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-2 px-3 pb-3">
          <Section title="طبقه‌بندی پیام">
            <Field
              name="intent (نیت)"
              value={label(INTENT_LABELS, debug.intent)}
              changed={changed("intent")}
              tone="key"
            />
            <Field
              name="mode (حالت)"
              value={label(MODE_LABELS, debug.mode)}
              changed={changed("mode")}
              tone="key"
            />
            <Field
              name="stage (مرحله خرید)"
              value={label(STAGE_LABELS, debug.stage)}
              changed={changed("stage")}
            />
            <Field
              name="value_driver (محرک انتخاب)"
              value={label(VALUE_DRIVER_LABELS, debug.valueDriver)}
              changed={changed("valueDriver")}
            />
            <Field
              name="objection (اعتراض فعال)"
              value={label(OBJECTION_LABELS, debug.objection)}
              changed={changed("objection")}
              tone="warn"
            />
            <Field
              name="product_id (محصول پین‌شده)"
              value={debug.productId}
              changed={changed("productId")}
            />
            <Field
              name="out_of_catalog (خارج از کاتالوگ)"
              value={debug.outOfCatalog ? "بله — این کالا را نداریم" : null}
              changed={changed("outOfCatalog")}
              tone="warn"
            />
            <Field
              name="sort (مرتب‌سازی صریح)"
              value={label(SORT_LABELS, debug.sort)}
              changed={changed("sort")}
            />
          </Section>

          <Section title="فیلترهای انباشته (explore_filters)">
            <Chips entries={filters} />
          </Section>

          <Section title="فیلتر واقعی اعمال‌شده روی کاتالوگ">
            <Field
              name="filter_status (وضعیت فیلتر)"
              value={label(FILTER_STATUS_LABELS, debug.filterStatus)}
              changed={changed("filterStatus")}
              tone={debug.filterStatus === "relaxed" ? "warn" : "neutral"}
            />
            <Field name="محصولات واجد شرایط" value={fa(debug.candidateCount)} />
            <Field
              name="فیلترهای حذف‌شده"
              value={
                debug.filtersDropped?.length
                  ? debug.filtersDropped.map((k) => FILTER_LABELS[k] ?? k).join("، ")
                  : null
              }
              changed={changed("filtersDropped")}
              tone="warn"
            />
            {effective.length > 0 && (
              <div className="pt-1">
                <Chips entries={effective} />
              </div>
            )}
          </Section>

          <Section title="مسیر گراف">
            <div className="flex flex-wrap items-center gap-1">
              {debug.path.map((node, i) => (
                <span key={node + "-" + i} className="flex items-center gap-1">
                  {i > 0 && <span className="text-muted-foreground/40">←</span>}
                  <span
                    className="rounded-md bg-background px-1.5 py-0.5 text-[11px] ring-1 ring-border"
                    title={node}
                  >
                    {NODE_LABELS[node] ?? node}
                  </span>
                </span>
              ))}
            </div>
          </Section>

          <Section title="بازیابی اطلاعات">
            <Field
              name="کاندیدای خام ← کانتکست نهایی"
              value={fa(debug.retrieved.rawCount) + " ← " + fa(debug.retrieved.contextCount)}
            />
            {types.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {types.map(([t, n]) => (
                  <span
                    key={t}
                    className="rounded-md bg-background px-1.5 py-0.5 text-[11px] ring-1 ring-border"
                  >
                    {TYPE_LABELS[t] ?? t}: {fa(n)}
                  </span>
                ))}
              </div>
            )}
            {debug.retrieved.scores.length > 0 && (
              <div className="pt-1 font-mono text-[10px] text-muted-foreground" dir="ltr">
                scores: {debug.retrieved.scores.join(" · ")}
              </div>
            )}
          </Section>

          <Section title={"محصولات نشان‌داده‌شده (" + fa(debug.shownProducts.length) + ")"}>
            {debug.shownProducts.length === 0 ? (
              <span className="text-[11px] text-muted-foreground/50">—</span>
            ) : (
              <ol className="flex flex-col gap-0.5">
                {debug.shownProducts.map((p, i) => (
                  <li key={p.id} className="flex items-center gap-1.5 text-[11px]">
                    <span className="text-muted-foreground/60">{fa(i + 1)}.</span>
                    <span className="truncate">{p.name ?? "—"}</span>
                    <span
                      className="ms-auto font-mono text-[10px] text-muted-foreground/50"
                      dir="ltr"
                    >
                      {p.id.slice(0, 12)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Section>

          {debug.excludedProductIds.length > 0 && (
            <Section title={"رد شده توسط مشتری (" + fa(debug.excludedProductIds.length) + ")"}>
              <div className="flex flex-wrap gap-1 font-mono text-[10px]" dir="ltr">
                {debug.excludedProductIds.map((id) => (
                  <span
                    key={id}
                    className="rounded bg-destructive/10 px-1 py-0.5 text-destructive"
                  >
                    {id.slice(0, 12)}
                  </span>
                ))}
              </div>
            </Section>
          )}

          <Section title="حافظه گفت‌وگو">
            <Field name="پیام‌های نگه‌داشته‌شده" value={fa(debug.messageCount)} />
            <Field
              name="خلاصه‌سازی"
              value={
                debug.hasSummary
                  ? "فعال (" + fa(debug.summaryChars) + " کاراکتر)"
                  : "غیرفعال"
              }
              changed={changed("hasSummary")}
            />
          </Section>
        </div>
      )}
    </div>
  )
}

---
name: rtl-design
description: RTL (right-to-left) design patterns for Persian/Arabic web apps using shadcn/ui and Tailwind CSS. ALWAYS load this skill the moment you hear "rtl", "راست به چپ", "فارسی", "persian", "arabic", "عربی", or any mention of UI components (sidebar, dialog, sheet, select, input, breadcrumb, dropdown, popover, tooltip, drawer, card, table, form) in a Persian/Arabic project context. Also triggers when the user asks about text direction, component layout, adding any new shadcn/ui component, fixing alignment issues, or adapting any LTR component for fa/ar locales. When in doubt, load it — it's better to have the RTL reference available than to miss a direction bug.
---

# RTL Design — Persian/Arabic Apps with shadcn/ui

Proven patterns for adapting shadcn/ui components to RTL in Next.js. All examples are derived from a production Persian app.

---

## 1. Root Setup

First and most important: set `dir` and `lang` on the `<html>` tag.

```tsx
// src/app/layout.tsx
<html lang="fa" dir="rtl">
  <body>...</body>
</html>
```

This alone makes the browser:
- Render text right-to-left
- Flip `flex-row` direction automatically
- Align scroll anchors correctly

> **Caveat:** Radix UI portals (Dialog, Select, Tooltip, Popover…) render outside the DOM tree and do **not** inherit `dir` from `<html>`. You must set `dir="rtl"` explicitly on portal content — see sections below.

---

## 2. Sidebar — Move to the Right

```tsx
<Sidebar collapsible="icon" side="right" className="border-l" dir="rtl">
```

| Property | LTR (default) | RTL (Persian) |
|----------|---------------|---------------|
| `side` prop | `"left"` | `"right"` |
| border | `border-r` | `border-l` |
| `dir` attr | omitted | `dir="rtl"` |
| active indicator | `absolute left-0` | `absolute right-0` |

**Active item indicator (right edge):**

```tsx
{active && (
  <span className="pointer-events-none absolute right-0 top-1 bottom-1 w-[3px] bg-primary rounded-full" />
)}
```

**Icon spacing inside menu items** — use `mr-2`, not `ml-2`:

```tsx
<Link href={item.href}>
  <Icon className="h-4 w-4 mr-2" />  {/* icon is to the RIGHT of nothing, LEFT of text */}
  <span>{item.title}</span>
</Link>
```

**Skeleton loading state** — keep `border-l`:

```tsx
<div className="w-[280px] bg-sidebar border-l hidden md:block">
```

---

## 3. Dialog — Close Button & Header

Move the × button from top-right to top-**left**:

```tsx
// src/components/ui/dialog.tsx — DialogContent
// LTR default: right-4 top-4
// RTL change:
<DialogPrimitive.Close className="absolute left-5 top-5 rounded-sm opacity-70 ...">
  <Cross2Icon className="h-4 w-4" />
  <span className="sr-only">بستن</span>
</DialogPrimitive.Close>
```

**DialogHeader** — flip text alignment:

```tsx
// LTR default:
"flex flex-col space-y-1.5 text-center sm:text-left"

// RTL:
"flex flex-col space-y-1.5 text-center sm:text-right"
```

---

## 4. Sheet — Close Button

Same as Dialog: move × to the left:

```tsx
// src/components/ui/sheet.tsx — SheetContent
// LTR: right-4 top-4
// RTL:
<SheetPrimitive.Close className="absolute left-4 top-4 z-50 ...">
```

**SheetHeader** text alignment:

```tsx
// LTR: "text-center sm:text-left"
// RTL: "text-center sm:text-right"
```

---

## 5. Select — Trigger Direction & Check Icon

**SelectTrigger** — use `flex-row-reverse` to push the chevron icon to the left:

```tsx
<SelectPrimitive.Trigger
  className={cn(
    "flex h-9 w-full items-center justify-between ... flex-row-reverse",
    className
  )}
>
  {children}
  <SelectPrimitive.Icon asChild>
    <ChevronDownIcon className="h-4 w-4 opacity-50" />
  </SelectPrimitive.Icon>
</SelectPrimitive.Trigger>
```

**SelectItem** — flip padding and move check icon to the right:

```tsx
// LTR: pl-8 pr-2, check icon at left-2
// RTL: pl-2 pr-8, check icon at right-2

<SelectPrimitive.Item
  className={cn(
    "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm ...",
    className
  )}
>
  <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
    <SelectPrimitive.ItemIndicator>
      <CheckIcon className="h-4 w-4" />
    </SelectPrimitive.ItemIndicator>
  </span>
  <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
</SelectPrimitive.Item>
```

---

## 6. Breadcrumb — Separator Direction

In RTL, the path flows right-to-left, so use `ChevronLeftIcon` (←) instead of `ChevronRightIcon` (→):

```tsx
// src/components/ui/breadcrumb.tsx
import { ChevronLeftIcon } from "@radix-ui/react-icons"

const BreadcrumbSeparator = ({ children, ...props }) => (
  <li role="presentation" aria-hidden="true" {...props}>
    {children ?? <ChevronLeftIcon />}  {/* ← for RTL */}
  </li>
)
```

---

## 7. DropdownMenu — Sub-trigger Chevron

```tsx
// LTR default:
<ChevronRightIcon className="ml-auto" />

// RTL:
<ChevronLeftIcon className="mr-auto" />
```

---

## 8. ScrollArea & Dialog Body — Explicit `dir`

Radix ScrollArea and portal-rendered content don't inherit `dir` from the document. Always set it explicitly:

```tsx
// Drawer (mobile)
<div className="w-full overflow-y-auto" dir="rtl">
  {children}
</div>

// ScrollArea (desktop)
<ScrollArea className="w-full">
  <div className="py-2 px-1" dir="rtl">
    {children}
  </div>
</ScrollArea>
```

---

## 9. Persian Numbers

Use `toLocaleString('fa-IR')` for displaying numbers in Persian digits:

```tsx
<span>{user.totalXp?.toLocaleString('fa-IR') || '۰'}</span>
<span>{remainingDays.toLocaleString('fa-IR')} روز مانده</span>
```

---

## 10. User Info Text Alignment

When displaying user name/details in RTL context:

```tsx
<div className="grid flex-1 text-right leading-tight">
  <span className="truncate font-semibold text-sm">{user.fullName}</span>
  <div className="flex items-center gap-1 text-sm text-muted-foreground" dir="rtl">
    <span>{user.totalXp?.toLocaleString('fa-IR') || '۰'}</span>
    <Image src="/star-coin.png" alt="coin" width={14} height={14} />
  </div>
</div>
```

---

## Checklist for Any New shadcn Component

Before using a new shadcn/ui component in a Persian project, verify:

- [ ] Close/dismiss buttons: moved from right → **left**?
- [ ] Header/footer alignment: `text-left` → **`text-right`**?
- [ ] Asymmetric padding flipped? (`pl-8 pr-2` → **`pl-2 pr-8`**)
- [ ] Chevron icons pointing the right way? (→ becomes **←**)
- [ ] Portal content has explicit **`dir="rtl"`**?
- [ ] Icon spacing: `ml-2` → **`mr-2`**?
- [ ] Numbers displayed with **`toLocaleString('fa-IR')`**?
- [ ] Sidebar/panel on the **right** side with `border-l`?

---

## Key Gotchas

**`dir="rtl"` on `<html>` is not enough for Radix portals.** Dialog, Select, Tooltip, Popover, and Sheet all use `ReactDOM.createPortal` and render outside the main tree. Without explicit `dir="rtl"` on their content, text alignment and icon positions will be wrong.

**`flex-row-reverse` vs `dir="rtl"`.** For simple icon-text pairs (like SelectTrigger), `flex-row-reverse` is the quickest fix. For actual text content, always prefer `dir="rtl"` — it handles bidirectional (bidi) text correctly.

**`mr-2` for icons before text in RTL.** In RTL flow, an icon sits to the right of text. Use `mr-2` (right margin = space between icon and the text that follows leftward). Using `ml-2` would push the icon away from the text, not toward it.

**`border-l` for sidebar.** When the sidebar is on the right, it needs a left border to separate it from main content — `border-l`, not `border-r`.

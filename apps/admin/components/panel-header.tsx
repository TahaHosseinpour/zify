"use client"

import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { HugeiconsIcon } from "@hugeicons/react"
import { Moon02Icon, Sun03Icon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { navTitle } from "@/lib/nav"

export function PanelHeader() {
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md">
      <SidebarTrigger className="text-muted-foreground" />
      <h1 className="flex-1 truncate text-sm font-semibold">{navTitle(pathname)}</h1>
      <ThemeToggle />
    </header>
  )
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="تغییر تم روشن و تیره"
      className="text-muted-foreground"
    >
      {/* Rendered by theme class rather than state, so the icon needs no mount guard. */}
      <HugeiconsIcon icon={Moon02Icon} strokeWidth={2} className="size-4 dark:hidden" />
      <HugeiconsIcon icon={Sun03Icon} strokeWidth={2} className="hidden size-4 dark:block" />
    </Button>
  )
}

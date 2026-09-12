"use client"

import Link from "next/link"
import Image from "next/image"
import { usePathname } from "next/navigation"
import { HugeiconsIcon } from "@hugeicons/react"
import { Logout01Icon, UserCircleIcon } from "@hugeicons/core-free-icons"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { navGroups, isNavItemActive } from "@/lib/nav"
import { toPersianDigits } from "@/lib/utils"

interface AppSidebarProps {
  side?: "left" | "right"
  shopName?: string
  userMobile?: string
}

export function AppSidebar({ side = "right", shopName, userMobile }: AppSidebarProps) {
  const pathname = usePathname()

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" })
    window.location.href = "/login"
  }

  return (
    <Sidebar side={side} collapsible="icon" dir="rtl" className="panel-theme panel-sidebar">
      <SidebarHeader className="h-14 justify-center border-b border-sidebar-border px-3 py-0">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-sidebar-primary/12 ring-1 ring-sidebar-border group-data-[collapsible=icon]:size-8">
            <Image src="/logo.png" alt="زیفای" width={22} height={22} className="rounded-full" />
          </span>
          <span className="flex min-w-0 flex-col gap-0.5 group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-bold text-sidebar-foreground">زیفای</span>
            <span className="truncate text-xs text-sidebar-foreground/55">
              {shopName ?? "پنل مدیریت"}
            </span>
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="px-1 py-2">
        {navGroups.map((group, index) => (
          <SidebarGroup key={group.label ?? index} className="py-1">
            {group.label && (
              <SidebarGroupLabel className="px-3 text-[11px] font-medium tracking-wide text-sidebar-foreground/50">
                {group.label}
              </SidebarGroupLabel>
            )}
            <SidebarMenu className="gap-1">
              {group.items.map((item) => {
                const isActive = isNavItemActive(item, pathname)
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={item.label}
                      className="h-10 gap-3 rounded-lg px-3 text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-primary/14 data-[active=true]:font-semibold data-[active=true]:text-sidebar-primary"
                    >
                      <Link href={item.href}>
                        <HugeiconsIcon
                          icon={item.icon}
                          strokeWidth={2}
                          className="size-[18px] shrink-0"
                        />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {isActive && (
                      <span className="pointer-events-none absolute inset-y-2 right-0 w-[3px] rounded-full bg-sidebar-primary" />
                    )}
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border p-2">
        <div className="flex items-center gap-2.5 px-2 py-1 group-data-[collapsible=icon]:hidden">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-sidebar-primary/14 text-sidebar-primary">
            <HugeiconsIcon icon={UserCircleIcon} strokeWidth={2} className="size-4" />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="text-[11px] text-sidebar-foreground/50">حساب شما</span>
            <span className="truncate text-xs font-medium text-sidebar-foreground/90">
              {userMobile ? toPersianDigits(userMobile) : "—"}
            </span>
          </span>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={handleLogout}
              tooltip="خروج از حساب"
              className="h-9 gap-3 rounded-lg px-3 text-sidebar-foreground/65 hover:bg-destructive/10 hover:text-destructive"
            >
              <HugeiconsIcon icon={Logout01Icon} strokeWidth={2} className="size-[18px]" />
              <span>خروج از حساب</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}

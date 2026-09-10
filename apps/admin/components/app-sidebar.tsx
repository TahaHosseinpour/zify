"use client"

import Link from "next/link"
import Image from "next/image"
import { usePathname } from "next/navigation"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ChartLineData02Icon,
  ShoppingBag01Icon,
  MessageQuestionIcon,
  Store01Icon,
  LinkSquare01Icon,
  UserMultiple02Icon,
  MessageMultiple01Icon,
  TestTube01Icon,
  Settings01Icon,
  Logout01Icon,
} from "@hugeicons/core-free-icons"
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

const navItems = [
  { href: "/dashboard", label: "آمار", icon: ChartLineData02Icon, exact: true },
  { href: "/dashboard/products", label: "محصولات", icon: ShoppingBag01Icon },
  { href: "/dashboard/faq", label: "سوالات متداول", icon: MessageQuestionIcon },
  { href: "/dashboard/business", label: "اطلاعات کسب‌وکار", icon: Store01Icon },
  { href: "/dashboard/channels", label: "کانال‌ها", icon: LinkSquare01Icon },
  { href: "/dashboard/users", label: "کاربران", icon: UserMultiple02Icon },
  { href: "/dashboard/chats", label: "گفت‌وگوها", icon: MessageMultiple01Icon },
  { href: "/dashboard/playground", label: "آزمایش گفت‌وگو", icon: TestTube01Icon },
  { href: "/dashboard/settings", label: "تنظیمات", icon: Settings01Icon },
]

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
    <Sidebar side={side} collapsible="icon" dir="rtl">
      <SidebarHeader className="border-b p-4">
        <div className="flex items-center gap-2">
          <Image src="/logo.png" alt="Zify" width={24} height={24} className="shrink-0 rounded-full" />
          <div className="flex flex-col gap-0.5 group-data-[collapsible=icon]:hidden">
            <span className="font-bold text-primary text-base">Zify</span>
            {shopName && (
              <span className="text-xs text-muted-foreground truncate">{shopName}</span>
            )}
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>منو</SidebarGroupLabel>
          <SidebarMenu>
            {navItems.map((item) => {
              const isActive = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href)
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive}
                    tooltip={item.label}
                  >
                    <Link href={item.href} className="flex items-center gap-2">
                      <HugeiconsIcon icon={item.icon} strokeWidth={2} className="size-4 shrink-0" />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t p-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={handleLogout} tooltip="خروج">
              <HugeiconsIcon icon={Logout01Icon} strokeWidth={2} className="size-4" />
              <span>{userMobile}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}

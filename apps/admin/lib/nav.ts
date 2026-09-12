import type { IconSvgElement } from "@hugeicons/react"
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
} from "@hugeicons/core-free-icons"

export interface NavItem {
  href: string
  label: string
  icon: IconSvgElement
  exact?: boolean
}

export interface NavGroup {
  label: string | null
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", label: "آمار", icon: ChartLineData02Icon, exact: true },
    ],
  },
  {
    label: "دانش دستیار",
    items: [
      { href: "/dashboard/products", label: "محصولات", icon: ShoppingBag01Icon },
      { href: "/dashboard/faq", label: "سوالات متداول", icon: MessageQuestionIcon },
      { href: "/dashboard/business", label: "اطلاعات کسب‌وکار", icon: Store01Icon },
    ],
  },
  {
    label: "مشتریان",
    items: [
      { href: "/dashboard/chats", label: "گفت‌وگوها", icon: MessageMultiple01Icon },
      { href: "/dashboard/users", label: "کاربران", icon: UserMultiple02Icon },
    ],
  },
  {
    label: "راه‌اندازی",
    items: [
      { href: "/dashboard/channels", label: "کانال‌ها", icon: LinkSquare01Icon },
      { href: "/dashboard/playground", label: "آزمایش گفت‌وگو", icon: TestTube01Icon },
      { href: "/dashboard/settings", label: "تنظیمات", icon: Settings01Icon },
    ],
  },
]

export function isNavItemActive(item: NavItem, pathname: string) {
  return item.exact ? pathname === item.href : pathname.startsWith(item.href)
}

export function navTitle(pathname: string) {
  const items = navGroups.flatMap((group) => group.items)
  const match = items.find((item) => isNavItemActive(item, pathname))
  return match?.label ?? "پنل مدیریت"
}

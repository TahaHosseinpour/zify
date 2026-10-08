import type { IconSvgElement } from "@hugeicons/react"
import {
  ChartLineData02Icon,
  ShoppingBag01Icon,
  MessageQuestionIcon,
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

// The platform operator's panel (/admin) - a different audience from the shop
// owner's dashboard above, sharing only the sidebar component.
export const adminNavGroups: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/admin", label: "فروشگاه‌ها", icon: ShoppingBag01Icon, exact: true },
      { href: "/admin/leads", label: "درخواست‌های خرید", icon: MessageMultiple01Icon },
      { href: "/admin/plans", label: "پلن‌ها و تنظیمات", icon: Settings01Icon },
    ],
  },
]

export function isNavItemActive(item: NavItem, pathname: string) {
  return item.exact ? pathname === item.href : pathname.startsWith(item.href)
}

export function navTitle(pathname: string) {
  const groups = pathname.startsWith("/admin") ? adminNavGroups : navGroups
  const items = groups.flatMap((group) => group.items)
  const match = items.find((item) => isNavItemActive(item, pathname))
  if (match) return match.label
  // Detail pages (/admin/shops/<id>) sit under no nav item of their own.
  return pathname.startsWith("/admin") ? "مدیریت پلتفرم" : "پنل مدیریت"
}

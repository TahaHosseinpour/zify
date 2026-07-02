import Link from "next/link"
import Image from "next/image"
import { HugeiconsIcon } from "@hugeicons/react"
import { Login02Icon } from "@hugeicons/core-free-icons"

const links = {
  محصول: [
    { href: "#modes", label: "حالت‌های دستیار" },
    { href: "#capabilities", label: "پنل مدیریت" },
  ],
  حساب‌کاربری: [{ href: "/login", label: "ورود به پنل" }],
}

export default function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-8 mb-10">
          <div className="col-span-2 sm:col-span-2">
            <Link href="/" className="inline-flex items-center gap-2.5 mb-3">
              <Image src="/logo.png" alt="زیفای" width={28} height={28} className="rounded-full object-contain" />
              <span className="font-bold text-foreground">زیفای</span>
            </Link>
            <p className="text-sm text-muted-foreground mb-4 max-w-xs leading-relaxed">
              دستیار فروش هوشمند برای فروشگاه‌های آنلاین در بستر تلگرام
            </p>
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 h-[34px] px-3 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs hover:bg-primary/15 transition-colors"
            >
              <HugeiconsIcon icon={Login02Icon} size={13} strokeWidth={2} />
              ورود به پنل
            </Link>
          </div>

          {Object.entries(links).map(([cat, items]) => (
            <div key={cat}>
              <h3 className="text-xs font-semibold text-foreground uppercase tracking-widest mb-3">{cat}</h3>
              <ul className="space-y-2">
                {items.map((item) => (
                  <li key={item.href + item.label}>
                    <Link href={item.href} className="text-sm text-muted-foreground hover:text-primary transition-colors">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="pt-6 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">© ۱۴۰۴ زیفای</p>
          <p className="text-xs text-muted-foreground">مدیر فروش شما در تلگرام</p>
        </div>
      </div>
    </footer>
  )
}

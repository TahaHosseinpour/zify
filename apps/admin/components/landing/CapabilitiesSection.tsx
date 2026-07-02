"use client"

import { motion, useInView } from "framer-motion"
import { useRef } from "react"
import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Package01Icon,
  MessageQuestionIcon,
  ArtificialIntelligence01Icon,
  ChartBarIncreasingIcon,
  ArrowLeft01Icon,
} from "@hugeicons/core-free-icons"

const panelItems = [
  { icon: Package01Icon, title: "مدیریت محصولات", desc: "افزودن تکی یا گروهی محصولات با تصویر و توضیحات" },
  { icon: MessageQuestionIcon, title: "سوالات متداول", desc: "پایگاه دانشی که دستیار برای پاسخ‌گویی از آن استفاده می‌کند" },
  { icon: ArtificialIntelligence01Icon, title: "شخصیت دستیار", desc: "تنظیم لحن و سبک پاسخ‌گویی متناسب با برند شما" },
  { icon: ChartBarIncreasingIcon, title: "گزارش فروش", desc: "رصد بازدیدکنندگان، نرخ تبدیل و نقاط ریزش مشتری" },
]

function PanelCard({ item, i }: { item: (typeof panelItems)[0]; i: number }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: "-40px" })
  const Icon = item.icon

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 18 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.4, delay: i * 0.08 }}
      className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition-all duration-200"
    >
      <div className="flex items-start gap-4">
        <div className="shrink-0 w-9 h-9 rounded-lg bg-primary/10 border border-primary/15 flex items-center justify-center mt-0.5">
          <HugeiconsIcon icon={Icon} size={17} strokeWidth={2} className="text-primary" />
        </div>
        <div>
          <h3 className="font-bold text-foreground text-sm mb-1">{item.title}</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
        </div>
      </div>
    </motion.div>
  )
}

export default function CapabilitiesSection() {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section id="capabilities" className="py-20 lg:py-28 border-t border-border">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div ref={ref}>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.45 }}
              className="text-primary text-xs font-semibold tracking-widest uppercase mb-3"
            >
              پنل مدیریت
            </motion.p>
            <motion.h2
              initial={{ opacity: 0, y: 14 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.45, delay: 0.07 }}
              className="text-2xl sm:text-3xl font-black text-foreground mb-4 leading-tight"
            >
              همه‌چیز را بدون کد نویسی مدیریت کنید
            </motion.h2>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.45, delay: 0.13 }}
              className="text-muted-foreground text-sm leading-relaxed mb-6"
            >
              دستیار شما از اطلاعات محصولات، سوالات متداول و شخصیتی که در پنل تعریف می‌کنید تغذیه می‌شود تا پاسخ‌هایی دقیق و فروش‌محور بدهد.
            </motion.p>
            <motion.div
              initial={{ opacity: 0 }}
              animate={inView ? { opacity: 1 } : {}}
              transition={{ duration: 0.4, delay: 0.2 }}
            >
              <Link
                href="/login"
                className="inline-flex items-center gap-2 h-[34px] px-5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-all"
              >
                ورود به پنل
                <HugeiconsIcon icon={ArrowLeft01Icon} size={14} strokeWidth={2} />
              </Link>
            </motion.div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            {panelItems.map((item, i) => (
              <PanelCard key={item.title} item={item} i={i} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

"use client"

import { motion, useInView } from "framer-motion"
import { useRef } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  CustomerServiceIcon,
  ShoppingCart01Icon,
  ArrowLeft01Icon,
  InformationCircleIcon,
} from "@hugeicons/core-free-icons"

const modes = [
  {
    icon: CustomerServiceIcon,
    name: "حالت مشاوره",
    link: "t.me/YourBot?start=shop_slug",
    items: [
      "ورود از لینک عمومی فروشگاه",
      "کشف نیاز، بودجه و هدف مشتری",
      "پیشنهاد و مقایسه محصولات مناسب",
      "هدایت از «سردرگمی» به «آماده‌ی خرید»",
    ],
  },
  {
    icon: ShoppingCart01Icon,
    name: "حالت فروش",
    link: "t.me/YourBot?start=shop_slug_productId",
    items: [
      "ورود از لینک یک محصول خاص",
      "توضیح متقاعدکننده‌ی محصول",
      "پاسخ به اعتراضات (قیمت، کیفیت)",
      "ایجاد انگیزه و ارائه لینک خرید",
    ],
  },
]

function ModeCard({ mode, i }: { mode: (typeof modes)[0]; i: number }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: "-40px" })
  const Icon = mode.icon

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 18 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.4, delay: i * 0.1 }}
      className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 transition-all duration-200"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-foreground text-base">{mode.name}</h3>
        <div className="shrink-0 w-10 h-10 rounded-lg bg-primary/10 border border-primary/15 flex items-center justify-center">
          <HugeiconsIcon icon={Icon} size={20} strokeWidth={2} className="text-primary" />
        </div>
      </div>
      <code dir="ltr" className="inline-block text-[11px] text-primary bg-accent rounded px-2 py-0.5 mb-3 font-mono">
        {mode.link}
      </code>
      <ul className="flex flex-col gap-1.5">
        {mode.items.map((it) => (
          <li key={it} className="flex items-start gap-1.5 text-sm text-muted-foreground leading-relaxed">
            <HugeiconsIcon icon={ArrowLeft01Icon} size={13} strokeWidth={2} className="text-primary mt-1 shrink-0" />
            {it}
          </li>
        ))}
      </ul>
    </motion.div>
  )
}

export default function ModesSection() {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section id="modes" className="py-20 lg:py-28 border-t border-border">
      <div ref={ref} className="max-w-5xl mx-auto px-4 sm:px-6">
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.45 }}
          className="text-primary text-xs font-semibold tracking-widest uppercase mb-3 text-center"
        >
          حالت‌های عملکردی دستیار
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 14 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.45, delay: 0.07 }}
          className="text-2xl sm:text-3xl font-black text-foreground mb-10 leading-tight text-center"
        >
          هر مشتری، از هر لینکی وارد شود، دقیقاً همان چیزی را می‌بیند که نیاز دارد
        </motion.h2>

        <div className="grid sm:grid-cols-2 gap-5">
          {modes.map((mode, i) => (
            <ModeCard key={mode.name} mode={mode} i={i} />
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="mt-5 flex items-center gap-2 justify-center text-xs text-muted-foreground bg-accent rounded-lg py-2.5 px-4"
        >
          <HugeiconsIcon icon={InformationCircleIcon} size={15} strokeWidth={2} className="text-primary shrink-0" />
          در هر دو حالت، پاسخ به سوالات متداول از پایگاه دانش فروشگاه شما در دسترس است
        </motion.div>
      </div>
    </section>
  )
}

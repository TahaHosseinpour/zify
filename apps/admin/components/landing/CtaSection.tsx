"use client"

import { motion, useInView } from "framer-motion"
import { useRef } from "react"
import Link from "next/link"
import Image from "next/image"
import { HugeiconsIcon } from "@hugeicons/react"
import { RocketIcon } from "@hugeicons/core-free-icons"
import StarBorder from "@/components/ui/StarBorder"

export default function CtaSection() {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section className="py-20 lg:py-28 border-t border-border">
      <div ref={ref} className="max-w-6xl mx-auto px-4 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.55 }}
          className="relative rounded-2xl overflow-hidden border border-primary/20"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% 0%, color-mix(in oklch, var(--primary), transparent 90%) 0%, transparent 70%), var(--card)",
          }}
        >
          <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />

          <div className="flex flex-col md:flex-row items-center gap-10 p-8 md:p-12">
            <motion.div
              initial={{ opacity: 0, scale: 0.85 }}
              animate={inView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="shrink-0 flex items-center justify-center w-28 h-28 md:w-32 md:h-32 rounded-3xl bg-primary/8 border border-primary/12 shadow-xl shadow-black/5"
            >
              <Image src="/logo.png" alt="زیفای" width={72} height={72} className="object-contain drop-shadow-lg rounded-full" />
            </motion.div>

            <div className="flex-1 text-center md:text-right">
              <motion.h2
                initial={{ opacity: 0, y: 14 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.45, delay: 0.18 }}
                className="text-2xl sm:text-3xl font-black text-primary mb-3"
              >
                همین حالا شروع کنید
              </motion.h2>
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.4, delay: 0.24 }}
                className="text-muted-foreground text-sm leading-relaxed mb-6 max-w-md md:mr-0 mx-auto"
              >
                در چند دقیقه فروشگاهتان را وصل کنید و بگذارید زیفای مشتریانتان را مشاوره بدهد، محصول پیشنهاد کند و نرخ تبدیل را افزایش دهد.
              </motion.p>

              <motion.div
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 1 } : {}}
                transition={{ duration: 0.4, delay: 0.3 }}
                className="flex items-center justify-center md:justify-start gap-6"
              >
                {[
                  { v: "رایگان", l: "شروع کار" },
                  { v: "بدون کد", l: "راه‌اندازی" },
                  { v: "۲۴/۷", l: "پشتیبانی دستیار" },
                ].map((s) => (
                  <div key={s.l} className="text-center">
                    <div className="font-bold text-foreground text-base">{s.v}</div>
                    <div className="text-xs text-muted-foreground">{s.l}</div>
                  </div>
                ))}
              </motion.div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.35 }}
              className="shrink-0 flex justify-center"
            >
              <StarBorder
                as={Link}
                href="/login"
                color="rgba(255,255,255,0.6)"
                speed="5s"
                className="rounded-lg"
                innerClassName="h-[34px] px-5 text-sm font-semibold leading-none text-primary-foreground rounded-lg bg-primary justify-center"
              >
                <HugeiconsIcon icon={RocketIcon} size={15} strokeWidth={2} />
                شروع رایگان
              </StarBorder>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

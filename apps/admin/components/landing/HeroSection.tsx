"use client"

import { motion, useInView } from "framer-motion"
import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import { SparklesIcon } from "@hugeicons/core-free-icons"
import GradientBlinds from "@/components/shared/GradientBlinds"
import StarBorder from "@/components/ui/StarBorder"

function CountUp({ to, duration = 1.8 }: { to: number; duration?: number }) {
  const [val, setVal] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })

  useEffect(() => {
    if (!inView) return
    const fps = 60
    const frames = Math.round(duration * fps)
    let frame = 0
    const id = setInterval(() => {
      frame++
      const progress = frame / frames
      const eased = 1 - Math.pow(1 - progress, 3)
      setVal(Math.round(eased * to))
      if (frame >= frames) clearInterval(id)
    }, 1000 / fps)
    return () => clearInterval(id)
  }, [inView, to, duration])

  return <span ref={ref}>{val.toLocaleString("fa-IR")}</span>
}

const innerCls = "h-[34px] px-5 text-xs sm:text-sm font-semibold rounded-lg border backdrop-blur-sm"
const innerPrimary = `${innerCls} text-white bg-[#7c3aed]/15 border-[#7c3aed]/30`
const innerWhite = `${innerCls} text-[#0a0a0a] bg-white border-transparent`

const stats = [
  { to: 2, suffix: "×", label: "افزایش نرخ تبدیل" },
  { to: 2, suffix: "", label: "حالت هوشمند دستیار" },
  { to: 24, suffix: "/۷", label: "پاسخگویی آنی" },
]

export default function HeroSection() {
  const [blindCount, setBlindCount] = useState(18)
  useEffect(() => {
    const update = () => setBlindCount(window.innerWidth < 768 ? 28 : 18)
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  return (
    <section
      className="relative w-full min-h-[88vh] sm:h-screen sm:min-h-[600px] flex flex-col overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 2, ease: "easeInOut" }}
      >
        <GradientBlinds
          gradientColors={["#4c2e9e", "#7c3aed", "#9d5ff5"]}
          angle={29}
          noise={0.11}
          blindCount={blindCount}
          blindMinWidth={60}
          spotlightRadius={0.5}
          spotlightSoftness={1}
          spotlightOpacity={1}
          mouseDampening={0.07}
          distortAmount={0}
          shineDirection="left"
          mixBlendMode="lighten"
          className="w-full h-full"
        />
      </motion.div>

      <div
        className="pointer-events-none absolute inset-0 z-10"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 50%, rgba(0,0,0,0.55) 0%, transparent 100%)",
        }}
      />

      <div
        className="pointer-events-none absolute bottom-0 inset-x-0 h-40 z-10"
        style={{ background: "linear-gradient(to top, var(--background) 0%, transparent 100%)" }}
      />

      <div className="relative z-20 flex flex-col items-center justify-center flex-1 px-4 text-center pt-[88px] sm:pt-0 pb-10 sm:pb-0">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mb-6"
        >
          <span
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium text-white/85 border border-white/15"
            style={{ background: "rgba(255,255,255,0.08)", backdropFilter: "blur(8px)" }}
          >
            <HugeiconsIcon icon={SparklesIcon} size={12} strokeWidth={2} className="text-[#c4a6ff]" />
            دستیار فروش هوشمند برای تلگرام شما
            <span className="w-1.5 h-1.5 rounded-full bg-[#c4a6ff] animate-pulse" />
          </span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="font-bold text-white leading-snug tracking-tight mb-4 max-w-3xl"
          style={{
            fontSize: "clamp(1.6rem, 3.8vw, 2.75rem)",
            textShadow: "0 2px 20px rgba(0,0,0,0.8), 0 1px 6px rgba(0,0,0,0.9)",
          }}
        >
          فروشگاهتان را به یک دستیار فروش هوشمند
          <br />
          داخل تلگرام مجهز کنید
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.32 }}
          className="text-white/50 text-sm sm:text-base max-w-lg mb-8 leading-relaxed"
        >
          بدون نیاز به دانش فنی، دستیاری بسازید که مشتریان را مشاوره می‌دهد، محصول پیشنهاد می‌کند و تا لحظه‌ی خرید همراهشان می‌ماند.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.44 }}
          className="flex flex-row items-center gap-2.5 flex-wrap justify-center"
        >
          <StarBorder
            as={Link}
            href="/login"
            color="#7c3aed"
            speed="5s"
            className="rounded-lg"
            innerClassName={innerPrimary}
          >
            شروع رایگان
          </StarBorder>

          <StarBorder
            as="a"
            href="#modes"
            color="rgba(255,255,255,0.5)"
            speed="7s"
            className="rounded-lg"
            innerClassName={innerWhite}
          >
            مشاهده حالت‌های دستیار
          </StarBorder>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-12 flex items-center"
        >
          {stats.map((s, i) => (
            <div
              key={s.label}
              className="text-center px-8"
              style={{
                borderLeft: i === 1 ? "1px solid rgba(255,255,255,0.1)" : undefined,
                borderRight: i === 1 ? "1px solid rgba(255,255,255,0.1)" : undefined,
              }}
            >
              <div className="text-xl sm:text-2xl font-black text-white">
                <CountUp to={s.to} />{s.suffix}
              </div>
              <div className="text-white/35 text-xs mt-0.5">{s.label}</div>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}

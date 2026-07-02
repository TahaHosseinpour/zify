"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import Image from "next/image"
import { motion, AnimatePresence } from "framer-motion"
import { HugeiconsIcon } from "@hugeicons/react"
import { Menu01Icon, Cancel01Icon, TelegramIcon } from "@hugeicons/core-free-icons"

const navLinks = [
  { href: "#modes", label: "حالت‌های دستیار" },
  { href: "#capabilities", label: "امکانات پنل" },
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 10)
    window.addEventListener("scroll", fn)
    return () => window.removeEventListener("scroll", fn)
  }, [])

  return (
    <>
      <motion.div
        initial={{ y: -60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="fixed inset-x-0 top-0 z-50 flex justify-center pt-4 px-4"
        dir="rtl"
      >
        <div
          className="w-full max-w-4xl flex items-center px-4 h-12 rounded-2xl"
          style={{
            background: scrolled ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.07)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: "1px solid rgba(255,255,255,0.08)",
            boxShadow: scrolled ? "0 4px 24px rgba(0,0,0,0.35)" : "none",
            transition: "background 0.3s, box-shadow 0.3s",
          }}
        >
          <Link href="/" className="flex items-center gap-2.5 shrink-0">
            <Image src="/logo.png" alt="زیفای" width={28} height={28} className="rounded-full" priority />
            <span className="text-white font-semibold text-sm">زیفای</span>
          </Link>

          <div className="hidden md:flex flex-1 items-center justify-center gap-0.5">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="px-3 py-1.5 text-sm text-white/60 hover:text-white rounded-lg hover:bg-white/6 transition-all duration-150 whitespace-nowrap"
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="flex-1 md:hidden" />

          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="hidden md:inline-flex items-center gap-1.5 h-[34px] px-4 rounded-lg bg-white text-[#0a0a0a] text-xs font-semibold hover:bg-white/90 transition-all"
            >
              <HugeiconsIcon icon={TelegramIcon} size={14} strokeWidth={2} />
              ورود به پنل
            </Link>
            <button
              onClick={() => setOpen(!open)}
              className="md:hidden p-1.5 rounded-lg hover:bg-white/8 transition-colors text-white/80"
              aria-label="منو"
            >
              <HugeiconsIcon icon={open ? Cancel01Icon : Menu01Icon} size={20} strokeWidth={2} />
            </button>
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="fixed inset-x-4 top-[72px] z-40 md:hidden rounded-2xl overflow-hidden"
            dir="rtl"
            style={{
              background: "rgba(10,10,10,0.94)",
              backdropFilter: "blur(20px)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <div className="p-3 flex flex-col gap-0.5">
              {navLinks.map((l, i) => (
                <motion.div
                  key={l.href}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06, duration: 0.2 }}
                >
                  <a
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className="block px-3 py-2.5 text-sm text-white/70 hover:text-white rounded-xl hover:bg-white/6 transition-colors"
                  >
                    {l.label}
                  </a>
                </motion.div>
              ))}
              <motion.div
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: navLinks.length * 0.06, duration: 0.2 }}
                className="mt-1"
              >
                <Link
                  href="/login"
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-center gap-1.5 h-[34px] px-3 rounded-lg bg-white text-[#0a0a0a] text-sm font-semibold"
                >
                  <HugeiconsIcon icon={TelegramIcon} size={15} strokeWidth={2} />
                  ورود به پنل
                </Link>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

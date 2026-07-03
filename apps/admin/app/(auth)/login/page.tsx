"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"
import { motion, AnimatePresence } from "framer-motion"
import { REGEXP_ONLY_DIGITS } from "input-otp"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp"
import { toast } from "sonner"

export default function LoginPage() {
  const router = useRouter()
  const [method, setMethod] = useState<"password" | "otp">("password")
  const [mobile, setMobile] = useState("")
  const [loading, setLoading] = useState(false)

  // password login
  const [password, setPassword] = useState("")

  // otp login
  const [step, setStep] = useState<"mobile" | "otp">("mobile")
  const [otp, setOtp] = useState("")
  const [timer, setTimer] = useState(0)

  function goAfterLogin(isNewUser: boolean) {
    router.push(isNewUser ? "/onboarding" : "/dashboard")
  }

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!mobile || mobile.length < 10) {
      toast.error("شماره موبایل معتبر نیست")
      return
    }
    if (!password) {
      toast.error("رمز عبور را وارد کنید")
      return
    }
    setLoading(true)
    try {
      const res = await fetch("/api/auth/login-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      toast.success("خوش آمدید!")
      goAfterLogin(data.isNewUser)
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "ورود ناموفق بود")
    } finally {
      setLoading(false)
    }
  }

  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault()
    if (!mobile || mobile.length < 10) {
      toast.error("شماره موبایل معتبر نیست")
      return
    }
    setLoading(true)
    try {
      const res = await fetch("/api/auth/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile }),
      })
      if (!res.ok) throw new Error()
      toast.success("کد تأیید ارسال شد")
      setStep("otp")
      setTimer(120)
      const interval = setInterval(() => {
        setTimer((t) => {
          if (t <= 1) { clearInterval(interval); return 0 }
          return t - 1
        })
      }, 1000)
    } catch {
      toast.error("خطا در ارسال کد")
    } finally {
      setLoading(false)
    }
  }

  async function handleVerifyOtp() {
    if (otp.length !== 6) return
    setLoading(true)
    try {
      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile, otp }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      toast.success("خوش آمدید!")
      goAfterLogin(data.isNewUser)
    } catch {
      toast.error("کد وارد شده اشتباه است")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="text-right">
        <Image src="/logo.png" alt="Zify" width={40} height={40} className="rounded-full mb-1" />
        <CardTitle className="text-2xl text-primary">Zify</CardTitle>
        <CardDescription>
          {method === "otp" && step === "otp"
            ? `کد ارسال‌شده به ${mobile} را وارد کنید`
            : "برای ورود به پنل وارد شوید"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AnimatePresence mode="wait">
          {method === "password" ? (
            <motion.form
              key="password"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              onSubmit={handlePasswordLogin}
              className="flex flex-col gap-4"
            >
              <div className="flex flex-col gap-2">
                <Label htmlFor="mobile-pw">شماره موبایل</Label>
                <Input
                  id="mobile-pw"
                  type="tel"
                  placeholder="09123456789"
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  dir="ltr"
                  className="text-left"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">رمز عبور</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  dir="ltr"
                  className="text-left"
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? "در حال ورود..." : "ورود"}
              </Button>
              <button
                type="button"
                className="text-primary underline text-sm"
                onClick={() => setMethod("otp")}
              >
                ورود با کد یکبار مصرف
              </button>
            </motion.form>
          ) : step === "mobile" ? (
            <motion.form
              key="otp-mobile"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              onSubmit={handleSendOtp}
              className="flex flex-col gap-4"
            >
              <div className="flex flex-col gap-2">
                <Label htmlFor="mobile-otp">شماره موبایل</Label>
                <Input
                  id="mobile-otp"
                  type="tel"
                  placeholder="09123456789"
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  dir="ltr"
                  className="text-left"
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? "در حال ارسال..." : "دریافت کد"}
              </Button>
              <button
                type="button"
                className="text-primary underline text-sm"
                onClick={() => setMethod("password")}
              >
                ورود با رمز عبور
              </button>
            </motion.form>
          ) : (
            <motion.div
              key="otp-code"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="flex flex-col gap-4 items-center"
            >
              <InputOTP
                maxLength={6}
                pattern={REGEXP_ONLY_DIGITS}
                value={otp}
                onChange={setOtp}
                onComplete={handleVerifyOtp}
              >
                <InputOTPGroup>
                  <InputOTPSlot index={0} />
                  <InputOTPSlot index={1} />
                  <InputOTPSlot index={2} />
                  <InputOTPSlot index={3} />
                  <InputOTPSlot index={4} />
                  <InputOTPSlot index={5} />
                </InputOTPGroup>
              </InputOTP>
              <Button
                onClick={handleVerifyOtp}
                disabled={otp.length !== 6 || loading}
                className="w-full"
              >
                {loading ? "در حال بررسی..." : "تأیید و ورود"}
              </Button>
              <div className="text-sm text-muted-foreground">
                {timer > 0 ? (
                  <span>{timer.toLocaleString("fa-IR")} ثانیه تا ارسال مجدد</span>
                ) : (
                  <button
                    type="button"
                    className="text-primary underline"
                    onClick={() => setStep("mobile")}
                  >
                    ارسال مجدد کد
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  )
}

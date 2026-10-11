"use client"

import { useState } from "react"
import Image from "next/image"
import { REGEXP_ONLY_DIGITS } from "input-otp"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp"
import { Label } from "@/components/ui/label"
import { toPersianDigits } from "@/lib/utils"

/** Sign-in for platform admins: username and password, then a code sent by
 * SMS. Deliberately its own page with its own credentials - it shares nothing
 * with the shop owner login at /login. */
export default function AdminLoginPage() {
  const [step, setStep] = useState<"password" | "otp">("password")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [otp, setOtp] = useState("")
  const [maskedMobile, setMaskedMobile] = useState("")
  const [loading, setLoading] = useState(false)

  async function submitPassword() {
    if (!username.trim() || !password) {
      toast.error("نام کاربری و رمز عبور را وارد کنید")
      return false
    }
    setLoading(true)
    try {
      const res = await fetch("/api/admin/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setMaskedMobile(data.mobile ?? "")
      setOtp("")
      setStep("otp")
      return true
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "ورود ناموفق بود")
      return false
    } finally {
      setLoading(false)
    }
  }

  async function submitOtp(code: string) {
    if (code.length !== 6) return
    setLoading(true)
    try {
      const res = await fetch("/api/admin/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp: code }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      // A full navigation, so the panel loads with the new session cookie.
      window.location.href = "/admin"
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "کد وارد شده اشتباه است")
      setOtp("")
      setLoading(false)
    }
  }

  return (
    <div className="panel-theme flex min-h-screen items-center justify-center bg-background p-4" dir="rtl">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Image src="/logo.png" alt="زیفای" width={44} height={44} className="mb-2 rounded-full" />
          <CardTitle>مدیریت پلتفرم</CardTitle>
          <CardDescription>
            {step === "otp"
              ? `کد ارسال‌شده به ${toPersianDigits(maskedMobile)} را وارد کنید`
              : "ورود مدیران زیفای"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {step === "password" ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                submitPassword()
              }}
              className="flex flex-col gap-4"
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="admin-username">نام کاربری</Label>
                <Input
                  id="admin-username"
                  dir="ltr"
                  className="text-right"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="admin-password">رمز عبور</Label>
                <PasswordInput
                  id="admin-password"
                  dir="ltr"
                  className="text-right"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={loading}>
                {loading ? "در حال بررسی..." : "ادامه"}
              </Button>
            </form>
          ) : (
            <div className="flex flex-col items-center gap-4">
              {/* Digits always read left to right, whatever the page direction. */}
              <div dir="ltr">
                <InputOTP
                  maxLength={6}
                  pattern={REGEXP_ONLY_DIGITS}
                  value={otp}
                  onChange={setOtp}
                  onComplete={submitOtp}
                  autoFocus
                >
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((index) => (
                      <InputOTPSlot key={index} index={index} />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
              </div>
              <Button onClick={() => submitOtp(otp)} disabled={otp.length !== 6 || loading} className="w-full">
                {loading ? "در حال بررسی..." : "تایید و ورود"}
              </Button>
              <div className="flex w-full items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground"
                  disabled={loading}
                  onClick={() => setStep("password")}
                >
                  بازگشت
                </button>
                <button
                  type="button"
                  className="text-primary hover:underline disabled:opacity-50"
                  disabled={loading}
                  onClick={async () => {
                    if (await submitPassword()) toast.success("کد جدید ارسال شد")
                  }}
                >
                  ارسال دوباره‌ی کد
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

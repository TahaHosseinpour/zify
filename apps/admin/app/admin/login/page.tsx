"use client"

import { useState } from "react"
import Image from "next/image"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { Label } from "@/components/ui/label"

/** Sign-in for platform admins: username and password. Deliberately its own
 * page with its own credentials - it shares nothing with the shop owner login
 * at /login. */
export default function AdminLoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!username.trim() || !password) {
      toast.error("نام کاربری و رمز عبور را وارد کنید")
      return
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
      // A full navigation, so the panel loads with the new session cookie.
      window.location.href = "/admin"
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "ورود ناموفق بود")
      setLoading(false)
    }
  }

  return (
    <div className="panel-theme flex min-h-screen items-center justify-center bg-background p-4" dir="rtl">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Image src="/logo.png" alt="زیفای" width={44} height={44} className="mb-2 rounded-full" />
          <CardTitle>مدیریت پلتفرم</CardTitle>
          <CardDescription>ورود مدیران زیفای</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit()
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
              {loading ? "در حال بررسی..." : "ورود"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

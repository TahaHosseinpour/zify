import { createHmac, timingSafeEqual } from "node:crypto"
import { cookies } from "next/headers"
import { prisma } from "@zify/db"
import type { Admin } from "@zify/db"
import {
  ADMIN_COOKIE,
  ADMIN_PENDING_COOKIE,
  ADMIN_PENDING_MINUTES,
  ADMIN_SESSION_HOURS,
  signAdminPendingToken,
  signAdminToken,
  verifyAdminPendingToken,
  verifyAdminToken,
} from "./admin-token"
import { appSecret } from "./secret"
import { sendOtp } from "./sms"

// Platform admins - the people who activate subscriptions - are their own
// kind of account, not a shop owner with extra rights. They have their own
// table (Admin), their own login page (/admin/login), their own cookies and
// their own kinds of token (lib/admin-token.ts). Nothing a shop owner can do
// to their own session turns it into this one, and nothing here reads or
// writes the owner session in lib/auth.ts.
//
// Signing in is two steps: username + password, then a one-time code sent by
// SMS to the mobile on the admin's record. Passing the first only earns a
// short-lived "pending" cookie; the session cookie exists only after the
// second.

const cookieBase = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  // Strict: the panel is never reached by following a link from elsewhere.
  sameSite: "strict" as const,
  path: "/",
}

// ── The SMS code ─────────────────────────────────────────────────────────────

/** Stored instead of the code itself, so reading the database never yields a
 * usable code. Keyed by the app secret and bound to the admin it was sent to. */
function hashOtp(adminId: string, otp: string): string {
  return createHmac("sha256", appSecret()).update(`admin-otp:${adminId}:${otp}`).digest("hex")
}

/** Send a fresh code to this admin's mobile and remember (a hash of) it. Any
 * earlier code stops working. */
export async function sendAdminOtp(admin: Admin): Promise<void> {
  const otp = await sendOtp(admin.mobile)
  await prisma.admin.update({
    where: { id: admin.id },
    data: {
      otpHash: hashOtp(admin.id, otp),
      otpExpiry: new Date(Date.now() + ADMIN_PENDING_MINUTES * 60 * 1000),
    },
  })
}

/** Check a code and, if it is right, use it up: a code works once. */
export async function consumeAdminOtp(admin: Admin, otp: string): Promise<boolean> {
  if (!admin.otpHash || !admin.otpExpiry || admin.otpExpiry < new Date()) return false

  const given = Buffer.from(hashOtp(admin.id, otp))
  const expected = Buffer.from(admin.otpHash)
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return false

  await prisma.admin.update({
    where: { id: admin.id },
    data: { otpHash: null, otpExpiry: null, lastLoginAt: new Date() },
  })
  return true
}

/** "0910***0050" - enough to recognise your own phone, not enough to learn a
 * number from a username and password alone. */
export function maskMobile(mobile: string): string {
  return mobile.length < 8 ? "***" : `${mobile.slice(0, 4)}***${mobile.slice(-4)}`
}

// ── Step one passed: the pending cookie ──────────────────────────────────────

export async function setAdminPending(adminId: string): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.set(ADMIN_PENDING_COOKIE, await signAdminPendingToken(adminId), {
    ...cookieBase,
    maxAge: 60 * ADMIN_PENDING_MINUTES,
  })
}

/** The active admin who passed the password step in this browser, or null. */
export async function getPendingAdmin(): Promise<Admin | null> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_PENDING_COOKIE)?.value
  if (!token) return null

  const adminId = await verifyAdminPendingToken(token)
  if (!adminId) return null

  const admin = await prisma.admin.findUnique({ where: { id: adminId } })
  return admin?.isActive ? admin : null
}

// ── Both steps passed: the session ───────────────────────────────────────────

export async function setAdminSession(adminId: string): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(ADMIN_PENDING_COOKIE)
  cookieStore.set(ADMIN_COOKIE, await signAdminToken(adminId), {
    ...cookieBase,
    maxAge: 60 * 60 * ADMIN_SESSION_HOURS,
  })
}

export async function clearAdminSession(): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(ADMIN_COOKIE)
  cookieStore.delete(ADMIN_PENDING_COOKIE)
}

/** The signed-in platform admin, or null. Loaded from the database on every
 * call rather than trusted from the token, so deactivating an admin takes
 * effect on their very next request, not when their session expires. */
export async function getAdmin(): Promise<Admin | null> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_COOKIE)?.value
  if (!token) return null

  const adminId = await verifyAdminToken(token)
  if (!adminId) return null

  const admin = await prisma.admin.findUnique({ where: { id: adminId } })
  return admin?.isActive ? admin : null
}

import { cookies } from "next/headers"
import { prisma } from "@zify/db"
import type { Admin } from "@zify/db"
import { ADMIN_COOKIE, ADMIN_SESSION_HOURS, signAdminToken, verifyAdminToken } from "./admin-token"

// Platform admins - the people who activate subscriptions - are their own
// kind of account, not a shop owner with extra rights. They have their own
// table (Admin), their own login page (/admin/login), their own cookie and
// their own kind of token (lib/admin-token.ts). Nothing a shop owner can do
// to their own session turns it into this one, and nothing here reads or
// writes the owner session in lib/auth.ts.
//
// Signing in is one step: username and password.

const cookieBase = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  // Strict: the panel is never reached by following a link from elsewhere.
  sameSite: "strict" as const,
  path: "/",
}

// Left behind in browsers that started a sign-in while it still had a second
// step; cleared on the way in and out so it does not linger.
const LEGACY_PENDING_COOKIE = "admin-pending"

export async function setAdminSession(adminId: string): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(LEGACY_PENDING_COOKIE)
  cookieStore.set(ADMIN_COOKIE, await signAdminToken(adminId), {
    ...cookieBase,
    maxAge: 60 * 60 * ADMIN_SESSION_HOURS,
  })
  await prisma.admin.update({ where: { id: adminId }, data: { lastLoginAt: new Date() } })
}

export async function clearAdminSession(): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(ADMIN_COOKIE)
  cookieStore.delete(LEGACY_PENDING_COOKIE)
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

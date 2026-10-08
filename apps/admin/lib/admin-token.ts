import { SignJWT, jwtVerify } from "jose"
import { appSecretBytes } from "./secret"

// The platform admin's tokens on their own, with no database or cookie access
// - so proxy.ts can check a session on every /admin request without pulling
// either in. lib/admin-auth.ts builds the actual sign-in on top of this.
//
// Signing in takes two steps (password, then a code sent by SMS), so there are
// two tokens: a short-lived "pending" one that only says "this browser passed
// the password step for this admin", and the session itself. Each is bound to
// its own audience, so neither can stand in for the other - and a shop owner's
// token, which has no audience at all, can stand in for neither.

export const ADMIN_COOKIE = "admin-token"
export const ADMIN_PENDING_COOKIE = "admin-pending"
const SESSION_AUDIENCE = "zify-platform-admin"
const PENDING_AUDIENCE = "zify-platform-admin-pending"
export const ADMIN_SESSION_HOURS = 12
export const ADMIN_PENDING_MINUTES = 5

async function sign(adminId: string, audience: string, expiresIn: string): Promise<string> {
  return new SignJWT({ adminId })
    .setProtectedHeader({ alg: "HS256" })
    .setAudience(audience)
    .setExpirationTime(expiresIn)
    .setIssuedAt()
    .sign(appSecretBytes())
}

async function verify(token: string, audience: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, appSecretBytes(), { audience })
    return typeof payload.adminId === "string" ? payload.adminId : null
  } catch {
    return null
  }
}

export const signAdminToken = (adminId: string) =>
  sign(adminId, SESSION_AUDIENCE, `${ADMIN_SESSION_HOURS}h`)

/** The admin id inside a session token, or null if it isn't a valid one. */
export const verifyAdminToken = (token: string) => verify(token, SESSION_AUDIENCE)

export const signAdminPendingToken = (adminId: string) =>
  sign(adminId, PENDING_AUDIENCE, `${ADMIN_PENDING_MINUTES}m`)

/** The admin id inside a pending (password-step-passed) token, or null. */
export const verifyAdminPendingToken = (token: string) => verify(token, PENDING_AUDIENCE)

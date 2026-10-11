import { SignJWT, jwtVerify } from "jose"
import { appSecretBytes } from "./secret"

// The platform admin's session token on its own, with no database or cookie
// access - so proxy.ts can check a session on every /admin request without
// pulling either in. lib/admin-auth.ts builds the actual sign-in on top of
// this.
//
// The token is bound to its own audience, so a shop owner's token, which has
// no audience at all, cannot stand in for it.

export const ADMIN_COOKIE = "admin-token"
const SESSION_AUDIENCE = "zify-platform-admin"
export const ADMIN_SESSION_HOURS = 12

export async function signAdminToken(adminId: string): Promise<string> {
  return new SignJWT({ adminId })
    .setProtectedHeader({ alg: "HS256" })
    .setAudience(SESSION_AUDIENCE)
    .setExpirationTime(`${ADMIN_SESSION_HOURS}h`)
    .setIssuedAt()
    .sign(appSecretBytes())
}

/** The admin id inside a session token, or null if it isn't a valid one. */
export async function verifyAdminToken(token: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, appSecretBytes(), { audience: SESSION_AUDIENCE })
    return typeof payload.adminId === "string" ? payload.adminId : null
  } catch {
    return null
  }
}

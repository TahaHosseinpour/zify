import { createHmac, randomUUID, timingSafeEqual } from "node:crypto"
import type { NextRequest } from "next/server"
import { appSecret } from "./secret"

// The storefront chat needs no login, so a visitor is whoever holds this
// cookie. The id inside it is issued and signed here, on the server.
//
// It used to be minted by the browser and sent in the request body, which made
// every per-visitor limit optional: a script could pick a fresh id per request
// and be a brand-new customer each time, with a brand-new allowance. An id the
// server never signed is now simply not an identity, and issuing new ones is
// rate-limited per IP by the chat route.

export const VISITOR_COOKIE = "zify-vid"
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365

function sign(id: string): string {
  return createHmac("sha256", appSecret()).update(`visitor:${id}`).digest("base64url")
}

export function newVisitorId(): string {
  return randomUUID()
}

/** The visitor id this request carries, or null when there is no cookie or its
 * signature doesn't check out. */
export function readVisitorId(req: NextRequest): string | null {
  const raw = req.cookies.get(VISITOR_COOKIE)?.value
  if (!raw) return null

  const dot = raw.lastIndexOf(".")
  if (dot <= 0) return null
  const id = raw.slice(0, dot)
  const given = Buffer.from(raw.slice(dot + 1))
  const expected = Buffer.from(sign(id))
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null
  return id
}

/** A `Set-Cookie` header value that makes `id` this browser's visitor id. */
export function visitorCookieHeader(id: string): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : ""
  return `${VISITOR_COOKIE}=${id}.${sign(id)}; Path=/; Max-Age=${ONE_YEAR_SECONDS}; HttpOnly; SameSite=Lax${secure}`
}

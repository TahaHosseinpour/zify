// The one signing secret behind session tokens and visitor cookies.
//
// Read at call time, never at import: `next build` runs with
// NODE_ENV=production and no runtime env, and must not fail just because a
// module that signs things was imported.

const DEV_FALLBACK = "fallback-secret-change-in-production"

export function appSecret(): string {
  const secret = process.env.JWT_SECRET
  if (secret) return secret
  if (process.env.NODE_ENV === "production") {
    // A known default here would let anyone mint a session for any account.
    throw new Error("JWT_SECRET is not set")
  }
  return DEV_FALLBACK
}

export function appSecretBytes(): Uint8Array {
  return new TextEncoder().encode(appSecret())
}

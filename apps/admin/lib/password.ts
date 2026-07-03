import { randomBytes, scrypt, timingSafeEqual } from "node:crypto"
import { promisify } from "node:util"

const scryptAsync = promisify(scrypt)
const KEY_LENGTH = 64

// Hash a plaintext password with a random salt. Stored as "salt:hash" (both hex)
// so verifyPassword can re-derive the key with the same salt.
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16).toString("hex")
  const derived = (await scryptAsync(password, salt, KEY_LENGTH)) as Buffer
  return `${salt}:${derived.toString("hex")}`
}

// Constant-time comparison against a stored "salt:hash". Returns false for any
// malformed / missing hash rather than throwing.
export async function verifyPassword(password: string, stored: string | null): Promise<boolean> {
  if (!stored) return false
  const [salt, key] = stored.split(":")
  if (!salt || !key) return false
  const keyBuffer = Buffer.from(key, "hex")
  const derived = (await scryptAsync(password, salt, KEY_LENGTH)) as Buffer
  if (keyBuffer.length !== derived.length) return false
  return timingSafeEqual(keyBuffer, derived)
}

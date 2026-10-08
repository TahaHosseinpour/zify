import { randomBytes, scrypt } from "node:crypto"
import { promisify } from "node:util"

const scryptAsync = promisify(scrypt)

// Mirror of apps/admin/lib/password.ts — keep the "salt:hash" (hex) format
// identical so the panel logins can verify a seeded password.
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16).toString("hex")
  const derived = (await scryptAsync(password, salt, 64)) as Buffer
  return `${salt}:${derived.toString("hex")}`
}

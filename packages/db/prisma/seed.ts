import { randomBytes, scrypt } from "node:crypto"
import { promisify } from "node:util"
import { PrismaClient } from "@prisma/client"

const scryptAsync = promisify(scrypt)

// Mirror of apps/admin/lib/password.ts — keep the "salt:hash" (hex) format
// identical so the admin login can verify a seeded password.
async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16).toString("hex")
  const derived = (await scryptAsync(password, salt, 64)) as Buffer
  return `${salt}:${derived.toString("hex")}`
}

const prisma = new PrismaClient()

async function main() {
  // Credentials default to the initial admin but can be overridden via env.
  const mobile = process.env.ADMIN_MOBILE || "09105860050"
  const password = process.env.ADMIN_PASSWORD || "Rt8d20dk3sed"

  const passwordHash = await hashPassword(password)

  const user = await prisma.user.upsert({
    where: { mobile },
    update: { password: passwordHash, isVerified: true },
    create: { mobile, password: passwordHash, isVerified: true },
  })

  console.log(`[seed] admin user ready: ${user.mobile} (id: ${user.id})`)
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })

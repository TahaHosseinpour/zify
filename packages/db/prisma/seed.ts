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

// One or more panel accounts to seed, as "mobile:password" pairs separated by
// commas (e.g. "09120000000:secret1,09120000001:secret2"). Falls back to the
// single ADMIN_MOBILE/ADMIN_PASSWORD pair (and then a hard-coded default) so
// existing single-admin setups keep working untouched.
function adminCredentials(): { mobile: string; password: string }[] {
  const list = process.env.ADMIN_USERS
  if (list) {
    return list
      .split(",")
      .map((pair) => pair.trim())
      .filter(Boolean)
      .map((pair) => {
        const [mobile, password] = pair.split(":")
        return { mobile, password }
      })
  }

  return [
    {
      mobile: process.env.ADMIN_MOBILE || "09105860050",
      password: process.env.ADMIN_PASSWORD || "Rt8d20dk3sed",
    },
  ]
}

async function main() {
  for (const { mobile, password } of adminCredentials()) {
    const passwordHash = await hashPassword(password)

    const user = await prisma.user.upsert({
      where: { mobile },
      update: { password: passwordHash, isVerified: true },
      create: { mobile, password: passwordHash, isVerified: true },
    })

    console.log(`[seed] admin user ready: ${user.mobile} (id: ${user.id})`)
  }
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })

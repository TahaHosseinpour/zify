import { PrismaClient } from "@prisma/client"
import { ADMINS, SHOP_OWNERS } from "./seed-accounts"

// Creates or refreshes the accounts listed in prisma/seed-accounts.ts. That
// file is the only source: nothing here reads an account from the
// environment, so every environment seeded from the same commit ends up with
// the same logins.

const prisma = new PrismaClient()

async function main() {
  for (const { mobile, passwordHash } of SHOP_OWNERS) {
    const user = await prisma.user.upsert({
      where: { mobile },
      update: { password: passwordHash, isVerified: true },
      create: { mobile, password: passwordHash, isVerified: true },
    })
    console.log(`[seed] shop owner ready: ${user.mobile}`)
  }

  // The list is the whole truth for admins: those on it are created or
  // brought in line with it, those no longer on it can no longer sign in. An
  // empty list changes nothing, so a seed run can never lock the platform out
  // of its own panel by accident.
  const usernames: string[] = []
  for (const admin of ADMINS) {
    const username = admin.username.trim().toLowerCase()
    usernames.push(username)
    await prisma.admin.upsert({
      where: { username },
      update: { password: admin.passwordHash, mobile: admin.mobile, isActive: true },
      create: { username, password: admin.passwordHash, mobile: admin.mobile },
    })
    console.log(`[seed] platform admin ready: ${username}`)
  }
  if (usernames.length > 0) {
    const removed = await prisma.admin.updateMany({
      where: { isActive: true, username: { notIn: usernames } },
      data: { isActive: false },
    })
    if (removed.count > 0) console.log(`[seed] deactivated ${removed.count} admin(s) no longer listed`)
  }
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })

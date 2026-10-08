import { createInterface } from "node:readline/promises"
import { hashPassword } from "./password-hash"

// Prints the hash of a password, for pasting into prisma/seed-accounts.ts.
//
//   bun run --cwd packages/db db:hash-password
//
// The password is asked for rather than taken as an argument, so it never
// lands in shell history or a process list.
const rl = createInterface({ input: process.stdin, output: process.stderr })
const password = await rl.question("Password: ")
rl.close()

if (!password) {
  console.error("No password given.")
  process.exit(1)
}
console.log(`passwordHash: "${await hashPassword(password)}",`)

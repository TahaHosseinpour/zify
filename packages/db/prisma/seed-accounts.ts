// The accounts every environment starts with, created or refreshed by
// prisma/seed.ts. This file is the single place they are defined: nothing
// about them is read from the environment.
//
// It is committed, so it holds password *hashes* (scrypt, "salt:hash"), never
// passwords. To add an account or change a password, generate a hash with
//
//   bun run --cwd packages/db db:hash-password
//
// and paste the line it prints here, then run db:seed.

export interface SeedShopOwner {
  mobile: string
  passwordHash: string
}

export interface SeedAdmin {
  /** Sign-in name at /admin/login. Case-insensitive. */
  username: string
  /** Where the sign-in code is sent by SMS. */
  mobile: string
  passwordHash: string
}

/** Shop owner logins (the panel at /login). */
export const SHOP_OWNERS: SeedShopOwner[] = [
  { mobile: "09105860050", passwordHash: "97d766a8d3dad09f5e46a522dd37009d:7c5fe3447b8e21e3de795fe6ae231469d9fb1409250ea64074681504b1ee339988040847673e5a11c6e1454cb82c0069fc275a05d5cf64bad138f80496580e52" },
  { mobile: "09105860051", passwordHash: "4990066bb45159f4c1b8b2876cd74b18:d053d3cc0c08b1bcede710f81ff70ed66861c4b01d3a76e86e097a5f4a787fefb39587ded98fc1f3f125d5242f245f4318771e14d55358bd7d72d6379cab1079" },
  { mobile: "09105860052", passwordHash: "a00faa91326099067b0a8edbfa2229ed:1065c6c14ed7809f3b6c8a62629157f989a58f8a3ce911d53abfc17b82c8bd3b13ccb02865ec85f1b577bfffb4d2de52a4327d44670b11e8e1b313e8d044d90f" },
]

/** Platform admins (the panel at /admin/login - they activate subscriptions).
 * This list is the whole truth: an admin removed from it is deactivated the
 * next time the seed runs. */
export const ADMINS: SeedAdmin[] = [
  {
    username: "TahaHosseinpour",
    mobile: "09105860050",
    passwordHash: "b38c6fcc831e2c79ef01a6e7b39b64ee:9f196d00b1cfe4ecdfa18c9b49e83714fcffcb3d4c5466a48edf3d0b738c2aaba9c16dd76424bddc38478b8033de6bb58295ac78f991377227540065a67e993f",
  },
]

import fs from "node:fs"
import path from "node:path"
import { afterAll, beforeAll, beforeEach, describe, expect, test } from "vitest"

// The gate is all database behaviour - counts, a per-shop lock, an atomic
// increment - so it is tested against the real Postgres from
// docker-compose.yml, on rows it creates and removes itself. Skipped (not
// failed) when the database isn't reachable, like the agent's DB tests.
//
// DATABASE_URL lives in the repo-root .env, which vitest doesn't load.
const rootEnv = path.resolve(__dirname, "../../../.env")
if (!process.env.DATABASE_URL && fs.existsSync(rootEnv)) {
  const match = /^DATABASE_URL\s*=\s*"?([^"\r\n]+)"?/m.exec(fs.readFileSync(rootEnv, "utf8"))
  if (match) process.env.DATABASE_URL = match[1]
}

const db = await import("@zify/db")
const {
  prisma,
  admitTurn,
  getQuotaStatus,
  quotaPeriodStart,
  shopDailyConversationCap,
  isConversationSpent,
  MAX_MESSAGES_PER_CONVERSATION,
  MAX_MESSAGE_CHARS,
  MAX_CONVERSATIONS_PER_END_USER_PER_DAY,
  MAX_CONVERSATION_COST_TOMAN,
  SUBSCRIPTION_MONTH_MS,
} = db

let available = true
try {
  await prisma.$queryRaw`SELECT 1 FROM subscriptions LIMIT 1`
} catch {
  available = false
}

const tag = `billing-test-${Date.now()}`
let shopId = ""
let userId = ""
let endUserSeq = 0

// A clock the tests move by hand. Each message is "sent" well after the last,
// so the minimum-gap rule never interferes unless a test is about it.
let clock = Date.now()
const tick = (ms = 10_000) => new Date((clock += ms))

async function newEndUser() {
  const endUser = await prisma.endUser.create({
    data: { shopId, webVisitorId: `${tag}-${endUserSeq++}` },
  })
  return endUser.id
}

async function subscribe(conversationsPerMonth: number, overrides: Record<string, unknown> = {}) {
  await prisma.subscription.deleteMany({ where: { shopId } })
  const startsAt = new Date(clock - 1000)
  return prisma.subscription.create({
    data: {
      shopId,
      planKey: "test",
      planName: "test",
      months: 1,
      startsAt,
      endsAt: new Date(startsAt.getTime() + SUBSCRIPTION_MONTH_MS),
      conversationsPerMonth,
      maxActiveProducts: 10,
      maxMonthlyProductUploads: 10,
      maxFaqItems: 10,
      maxBroadcastsPerMonth: 1,
      priceToman: 1,
      ...overrides,
    },
  })
}

const say = (endUserId: string, message = "سلام", extra: Record<string, unknown> = {}) =>
  admitTurn({ shopId, endUserId, message, mode: "explore", now: tick(), ...extra })

describe.skipIf(!available)("admitTurn", () => {
  beforeAll(async () => {
    const user = await prisma.user.create({ data: { mobile: tag } })
    userId = user.id
    const shop = await prisma.shop.create({ data: { slug: tag, name: tag, ownerId: user.id } })
    shopId = shop.id
  })

  beforeEach(async () => {
    await prisma.conversation.deleteMany({ where: { shopId } })
    await prisma.endUser.deleteMany({ where: { shopId } })
    await prisma.subscription.deleteMany({ where: { shopId } })
  })

  afterAll(async () => {
    if (!shopId) return
    await prisma.conversation.deleteMany({ where: { shopId } })
    await prisma.endUser.deleteMany({ where: { shopId } })
    await prisma.subscription.deleteMany({ where: { shopId } })
    await prisma.shop.delete({ where: { id: shopId } })
    await prisma.user.delete({ where: { id: userId } })
  })

  test("a shop with no subscription is off", async () => {
    const result = await say(await newEndUser())
    expect(result).toMatchObject({ ok: false, reason: "no_subscription" })
  })

  test("an expired subscription is off, a cancelled one too", async () => {
    const endUser = await newEndUser()
    await subscribe(100, { endsAt: new Date(clock - 500) })
    expect(await say(endUser)).toMatchObject({ ok: false, reason: "no_subscription" })

    await subscribe(100, { status: "cancelled" })
    expect(await say(endUser)).toMatchObject({ ok: false, reason: "no_subscription" })
  })

  test("the first message bills exactly one conversation; later ones bill nothing more", async () => {
    await subscribe(100)
    const endUser = await newEndUser()

    const first = await say(endUser)
    expect(first.ok).toBe(true)
    expect((await getQuotaStatus(shopId, new Date(clock))).conversationsUsed).toBe(1)

    const second = await say(endUser)
    expect(second.ok && first.ok && second.conversation.id === first.conversation.id).toBe(true)
    expect(second.ok && second.conversation.userMessageCount).toBe(2)
    expect((await getQuotaStatus(shopId, new Date(clock))).conversationsUsed).toBe(1)
  })

  test("a conversation holds the message cap and no more; the next message opens and bills a new one", async () => {
    await subscribe(100)
    const endUser = await newEndUser()

    const ids = new Set<string>()
    for (let i = 0; i < MAX_MESSAGES_PER_CONVERSATION; i++) {
      const result = await say(endUser)
      expect(result.ok).toBe(true)
      if (result.ok) ids.add(result.conversation.id)
    }
    expect(ids.size).toBe(1)

    const overflow = await say(endUser)
    expect(overflow.ok).toBe(true)
    if (overflow.ok) {
      expect(ids.has(overflow.conversation.id)).toBe(false)
      expect(overflow.conversation.userMessageCount).toBe(1)
    }
    expect((await getQuotaStatus(shopId, new Date(clock))).conversationsUsed).toBe(2)
  })

  test("a conversation near its cost ceiling is closed even with messages to spare", async () => {
    await subscribe(100)
    const endUser = await newEndUser()
    const first = await say(endUser)
    expect(first.ok).toBe(true)
    if (!first.ok) return

    // As apps/agent/app/metering.py would after an unusually expensive turn.
    await prisma.conversation.update({
      where: { id: first.conversation.id },
      data: { costToman: MAX_CONVERSATION_COST_TOMAN - 100 },
    })

    const next = await say(endUser)
    expect(next.ok && next.conversation.id !== first.conversation.id).toBe(true)
  })

  test("when the period's conversations are gone, new customers are refused and nothing is billed", async () => {
    await subscribe(2)
    expect((await say(await newEndUser())).ok).toBe(true)
    expect((await say(await newEndUser())).ok).toBe(true)

    const third = await say(await newEndUser())
    expect(third).toMatchObject({ ok: false, reason: "quota_exhausted" })
    expect((await getQuotaStatus(shopId, new Date(clock))).conversationsUsed).toBe(2)
  })

  test("a customer already mid-conversation can finish it after the quota runs out", async () => {
    await subscribe(1)
    const endUser = await newEndUser()
    expect((await say(endUser)).ok).toBe(true)
    // Quota is now full, but this conversation was already paid for.
    expect((await say(endUser)).ok).toBe(true)
  })

  test("one customer cannot start more than the daily number of conversations", async () => {
    await subscribe(1_000)
    const endUser = await newEndUser()

    for (let c = 0; c < MAX_CONVERSATIONS_PER_END_USER_PER_DAY; c++) {
      for (let m = 0; m < MAX_MESSAGES_PER_CONVERSATION; m++) {
        expect((await say(endUser)).ok).toBe(true)
      }
    }
    expect(await say(endUser)).toMatchObject({ ok: false, reason: "end_user_daily_cap" })

    // The shop owner testing in the playground is not a customer.
    expect((await say(endUser, "سلام", { isOwner: true })).ok).toBe(true)
  })

  test("a shop cannot burn more than its daily share of the month in one day", async () => {
    const subscription = await subscribe(200)
    const cap = shopDailyConversationCap(subscription.conversationsPerMonth)
    expect(cap).toBe(20)

    for (let i = 0; i < cap; i++) {
      expect((await say(await newEndUser())).ok).toBe(true)
    }
    expect(await say(await newEndUser())).toMatchObject({ ok: false, reason: "shop_daily_cap" })
  })

  test("an over-long message is refused before anything else is looked at", async () => {
    await subscribe(100)
    const result = await say(await newEndUser(), "ا".repeat(MAX_MESSAGE_CHARS + 1))
    expect(result).toMatchObject({ ok: false, reason: "message_too_long" })
    expect((await getQuotaStatus(shopId, new Date(clock))).conversationsUsed).toBe(0)
  })

  test("two messages too close together: the second is refused", async () => {
    await subscribe(100)
    const endUser = await newEndUser()
    expect((await say(endUser)).ok).toBe(true)

    const tooSoon = await admitTurn({
      shopId,
      endUserId: endUser,
      message: "سلام",
      mode: "explore",
      now: tick(500),
    })
    expect(tooSoon).toMatchObject({ ok: false, reason: "too_fast" })
  })

  test("a blocked customer is refused", async () => {
    await subscribe(100)
    const endUser = await newEndUser()
    await prisma.endUser.update({ where: { id: endUser }, data: { isBlocked: true } })
    expect(await say(endUser)).toMatchObject({ ok: false, reason: "blocked" })
  })

  test("simultaneous first messages cannot oversell the last conversation", async () => {
    await subscribe(1)
    const customers = await Promise.all([newEndUser(), newEndUser(), newEndUser(), newEndUser()])
    const now = tick()

    const results = await Promise.all(
      customers.map((endUserId) =>
        admitTurn({ shopId, endUserId, message: "سلام", mode: "explore", now }),
      ),
    )
    expect(results.filter((r) => r.ok)).toHaveLength(1)
    expect((await getQuotaStatus(shopId, now)).conversationsUsed).toBe(1)
  })
})

describe("quota arithmetic", () => {
  const startsAt = new Date("2026-01-01T00:00:00Z")

  test("a multi-month subscription is back-to-back 30-day periods, each with its own quota", () => {
    const at = (days: number) => new Date(startsAt.getTime() + days * 24 * 60 * 60 * 1000)
    expect(quotaPeriodStart({ startsAt }, at(0))).toEqual(startsAt)
    expect(quotaPeriodStart({ startsAt }, at(29))).toEqual(startsAt)
    expect(quotaPeriodStart({ startsAt }, at(30))).toEqual(at(30))
    expect(quotaPeriodStart({ startsAt }, at(75))).toEqual(at(60))
  })

  test("the daily cap is a tenth of the month, with a floor for tiny plans", () => {
    expect(shopDailyConversationCap(5_000)).toBe(500)
    expect(shopDailyConversationCap(500)).toBe(50)
    expect(shopDailyConversationCap(20)).toBe(10)
  })

  test("a conversation is spent at the message cap or within one turn of the cost ceiling", () => {
    const fresh = { userMessageCount: 1, costToman: 0 as never }
    expect(isConversationSpent(fresh)).toBe(false)
    expect(isConversationSpent({ ...fresh, userMessageCount: MAX_MESSAGES_PER_CONVERSATION })).toBe(true)
    expect(isConversationSpent({ ...fresh, costToman: 1_900 as never })).toBe(true)
    expect(isConversationSpent({ ...fresh, costToman: 1_800 as never })).toBe(false)
  })
})

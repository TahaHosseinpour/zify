import { prisma, SUBSCRIPTION_MONTH_MS } from "@zify/db"
import type { Subscription } from "@zify/db"
import {
  CUSTOM_MAX_CONVERSATIONS,
  CUSTOM_MIN_CONVERSATIONS,
  CUSTOM_PLAN_KEY,
  customPlanPrice,
  isPlanDuration,
  planPrice,
} from "@zify/shared"

export type ActivationInput = {
  shopId: string
  planKey: string
  months: number
  /** Only read for the custom plan. */
  conversationsPerMonth?: number
  note?: string
  adminId: string
}

export type ActivationResult =
  | { ok: true; subscription: Subscription }
  | { ok: false; error: string }

/**
 * Switch a plan on for a shop, starting now. Payment has already been taken by
 * hand; this is the record of it and the thing that turns the assistant on.
 *
 * A shop has one subscription in force at a time: activating a new one ends
 * whatever was active, so an upgrade is one action rather than two.
 */
export async function activateSubscription(input: ActivationInput): Promise<ActivationResult> {
  const { shopId, planKey, months, note, adminId } = input
  if (!isPlanDuration(months)) return { ok: false, error: "مدت اشتراک باید ۱، ۳ یا ۱۲ ماه باشد." }

  const shop = await prisma.shop.findUnique({ where: { id: shopId } })
  if (!shop) return { ok: false, error: "فروشگاه یافت نشد." }

  const plans = await prisma.plan.findMany({ orderBy: { conversationsPerMonth: "asc" } })

  let terms: Pick<
    Subscription,
    | "planKey"
    | "planName"
    | "conversationsPerMonth"
    | "maxActiveProducts"
    | "maxMonthlyProductUploads"
    | "maxFaqItems"
    | "maxBroadcastsPerMonth"
    | "priceToman"
  >

  if (planKey === CUSTOM_PLAN_KEY) {
    const conversations = Math.floor(Number(input.conversationsPerMonth))
    if (
      !Number.isFinite(conversations) ||
      conversations < CUSTOM_MIN_CONVERSATIONS ||
      conversations > CUSTOM_MAX_CONVERSATIONS
    ) {
      return {
        ok: false,
        error: `تعداد گفتگوی پلن سفارشی باید بین ${CUSTOM_MIN_CONVERSATIONS.toLocaleString("fa-IR")} و ${CUSTOM_MAX_CONVERSATIONS.toLocaleString("fa-IR")} باشد.`,
      }
    }
    // The catalog limits of a custom plan are those of the largest standard
    // plan it is at least as big as (they cost next to nothing either way -
    // what a custom plan is priced on is its conversations).
    const tier = [...plans].reverse().find((p) => p.conversationsPerMonth <= conversations) ?? plans[0]
    if (!tier) return { ok: false, error: "هیچ پلنی تعریف نشده است." }
    terms = {
      planKey: CUSTOM_PLAN_KEY,
      planName: "سفارشی",
      conversationsPerMonth: conversations,
      maxActiveProducts: tier.maxActiveProducts,
      maxMonthlyProductUploads: tier.maxMonthlyProductUploads,
      maxFaqItems: tier.maxFaqItems,
      maxBroadcastsPerMonth: tier.maxBroadcastsPerMonth,
      priceToman: customPlanPrice(conversations, months),
    }
  } else {
    const plan = plans.find((p) => p.key === planKey)
    if (!plan) return { ok: false, error: "پلن یافت نشد." }
    terms = {
      planKey: plan.key,
      planName: plan.name,
      conversationsPerMonth: plan.conversationsPerMonth,
      maxActiveProducts: plan.maxActiveProducts,
      maxMonthlyProductUploads: plan.maxMonthlyProductUploads,
      maxFaqItems: plan.maxFaqItems,
      maxBroadcastsPerMonth: plan.maxBroadcastsPerMonth,
      priceToman: planPrice(plan, months),
    }
  }

  const startsAt = new Date()
  const endsAt = new Date(startsAt.getTime() + months * SUBSCRIPTION_MONTH_MS)

  const subscription = await prisma.$transaction(async (tx) => {
    await tx.subscription.updateMany({
      where: { shopId, status: "active", endsAt: { gt: startsAt } },
      data: { status: "cancelled" },
    })
    return tx.subscription.create({
      data: {
        shopId,
        ...terms,
        months,
        startsAt,
        endsAt,
        note: note?.trim() || null,
        activatedById: adminId,
      },
    })
  })
  return { ok: true, subscription }
}

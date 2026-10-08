import { describe, expect, test } from "vitest"
import {
  CONVERSATION_COST_CAP_TOMAN,
  CUSTOM_MAX_CONVERSATIONS,
  CUSTOM_MIN_CONVERSATIONS,
  CUSTOM_PRICE_PER_CONVERSATION_TOMAN,
  PLAN_DURATIONS_MONTHS,
  clampCustomConversations,
  customPlanPrice,
  isPlanDuration,
  maxMonthlyCostToman,
  planPrice,
} from "@zify/shared"

// The two plans as seeded by migration 0004.
const SMALL = { monthlyPriceToman: 1_800_000, discountPercent3Months: 0, discountPercent12Months: 0 }
const LARGE = { monthlyPriceToman: 18_000_000, discountPercent3Months: 0, discountPercent12Months: 0 }

describe("plan pricing", () => {
  test("the seeded plans cost what was agreed", () => {
    expect(planPrice(SMALL, 1)).toBe(1_800_000)
    expect(planPrice(LARGE, 1)).toBe(18_000_000)
  })

  test("a longer period is that many months at the same rate when there is no discount", () => {
    expect(planPrice(SMALL, 3)).toBe(5_400_000)
    expect(planPrice(SMALL, 12)).toBe(21_600_000)
  })

  test("a duration discount applies only to its own duration", () => {
    const plan = { monthlyPriceToman: 1_000_000, discountPercent3Months: 10, discountPercent12Months: 20 }
    expect(planPrice(plan, 1)).toBe(1_000_000)
    expect(planPrice(plan, 3)).toBe(2_700_000)
    expect(planPrice(plan, 12)).toBe(9_600_000)
  })

  test("only 1, 3 and 12 months are durations", () => {
    expect(PLAN_DURATIONS_MONTHS).toEqual([1, 3, 12])
    expect(isPlanDuration(3)).toBe(true)
    expect(isPlanDuration(2)).toBe(false)
    expect(isPlanDuration("3")).toBe(false)
  })
})

describe("the cost floor under every price", () => {
  // The whole commercial model: a shop that uses every conversation it
  // bought, each one to its cost ceiling, must still cost less than it paid.
  test("the seeded plans are priced 20% above the most they can cost", () => {
    expect(SMALL.monthlyPriceToman).toBe(maxMonthlyCostToman(500) * 1.2)
    expect(LARGE.monthlyPriceToman).toBe(maxMonthlyCostToman(5_000) * 1.2)
  })

  test("the custom rate is the conversation ceiling plus the markup", () => {
    expect(CUSTOM_PRICE_PER_CONVERSATION_TOMAN).toBe(3_600)
    expect(CUSTOM_PRICE_PER_CONVERSATION_TOMAN).toBeGreaterThan(CONVERSATION_COST_CAP_TOMAN)
  })

  test.each([100, 500, 2_300, 5_000, 100_000])(
    "a custom plan of %i conversations is priced above its cost ceiling for every duration",
    (conversations) => {
      for (const months of PLAN_DURATIONS_MONTHS) {
        expect(customPlanPrice(conversations, months)).toBeGreaterThan(
          maxMonthlyCostToman(conversations) * months,
        )
      }
    },
  )
})

describe("custom plan size", () => {
  test("is rounded to the step and held inside the allowed range", () => {
    expect(clampCustomConversations(1_540)).toBe(1_500)
    expect(clampCustomConversations(1_550)).toBe(1_600)
    expect(clampCustomConversations(3)).toBe(CUSTOM_MIN_CONVERSATIONS)
    expect(clampCustomConversations(9_999_999)).toBe(CUSTOM_MAX_CONVERSATIONS)
  })

  test("the price is computed from the clamped size, not the raw input", () => {
    expect(customPlanPrice(3, 1)).toBe(CUSTOM_MIN_CONVERSATIONS * CUSTOM_PRICE_PER_CONVERSATION_TOMAN)
  })
})

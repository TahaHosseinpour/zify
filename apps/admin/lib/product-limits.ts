import { prisma, getShopLimits } from "@zify/db";

// Two ceilings on a shop's catalog, both read from its subscription (or from
// the no-subscription defaults, so an owner can build a catalog before paying
// - see packages/db/src/billing.ts):
//
//  - how many *active* products it can have at once (each one is a standing
//    embedding, kept until deleted), and
//  - a rolling-month cap shared by product *creates and edits* - each costs
//    an embedding call the same way, so deleting and recreating (or just
//    repeatedly editing) products would otherwise be a free way around the
//    first ceiling. Lazy reset (like apps/agent/app/usage.py's token
//    counters): checked/rolled-forward here on every create/update attempt,
//    no cron needed.
const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

export type ProductLimitCheck =
  | { ok: true }
  | { ok: false; reason: "active_cap" | "monthly_cap"; limit: number };

async function checkAndRecordMonthlyCap(shopId: string, max: number): Promise<ProductLimitCheck> {
  const shop = await prisma.shop.findUniqueOrThrow({ where: { id: shopId } });
  const now = new Date();
  const expired = now.getTime() >= shop.monthlyUploadsResetAt.getTime();
  const currentCount = expired ? 0 : shop.monthlyProductUploads;

  if (currentCount >= max) {
    return { ok: false, reason: "monthly_cap", limit: max };
  }

  await prisma.shop.update({
    where: { id: shopId },
    data: {
      monthlyProductUploads: currentCount + 1,
      monthlyUploadsResetAt: expired ? new Date(now.getTime() + MONTH_MS) : shop.monthlyUploadsResetAt,
    },
  });
  return { ok: true };
}

/**
 * Call before `prisma.product.create`: checks the standing active-product
 * ceiling (a pure read - deletes/creates elsewhere keep that count accurate
 * on their own) *and* the monthly create/edit cap, recording against the
 * latter on success.
 */
export async function checkAndRecordProductUpload(shopId: string): Promise<ProductLimitCheck> {
  const limits = await getShopLimits(shopId);
  const activeCount = await prisma.product.count({ where: { shopId, isActive: true } });
  if (activeCount >= limits.maxActiveProducts) {
    return { ok: false, reason: "active_cap", limit: limits.maxActiveProducts };
  }

  return checkAndRecordMonthlyCap(shopId, limits.maxMonthlyProductUploads);
}

/**
 * Call before `prisma.product.update`. Only the monthly cap applies here -
 * editing an existing product doesn't change how many active products the
 * shop is standing on, so the active-product ceiling doesn't apply.
 */
export async function checkAndRecordProductEdit(shopId: string): Promise<ProductLimitCheck> {
  const limits = await getShopLimits(shopId);
  return checkAndRecordMonthlyCap(shopId, limits.maxMonthlyProductUploads);
}

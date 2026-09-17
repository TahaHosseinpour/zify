import { prisma } from "@zify/db"
import type { Shop, EndUser } from "@zify/db"

/** Resolve (shop, endUser) for the storefront's public API routes, without
 * creating an EndUser row when there isn't one yet (unlike the chat route's
 * own upsert - a usage/history check for a visitor who has never actually
 * chatted has nothing to report, and shouldn't manufacture an EndUser row
 * just to say so). */
export async function resolveShopVisitor(
  slug: string,
  webVisitorId: string,
): Promise<{ shop: Shop; endUser: EndUser | null } | null> {
  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return null

  const endUser = await prisma.endUser.findUnique({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId } },
  })
  return { shop, endUser }
}

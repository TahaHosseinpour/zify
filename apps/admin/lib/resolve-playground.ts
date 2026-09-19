import { prisma, PLAYGROUND_WEB_VISITOR_ID } from "@zify/db"
import type { Shop, EndUser } from "@zify/db"
import { getSession } from "./auth"

/** The signed-in shop owner's own shop — every playground route's starting
 * point, same as the rest of the dashboard's API routes. */
export async function resolvePlaygroundShop(): Promise<Shop | null> {
  const session = await getSession()
  if (!session) return null

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })
  return user?.shops[0] ?? null
}

/** Same as `resolvePlaygroundShop`, plus the sentinel EndUser row that
 * represents "this shop owner testing their own bot" (see
 * packages/db/src/playground.ts) - null when they haven't sent a playground
 * message yet, mirroring resolveShopVisitor's contract for the real
 * storefront. */
export async function resolvePlaygroundVisitor(): Promise<{ shop: Shop; endUser: EndUser | null } | null> {
  const shop = await resolvePlaygroundShop()
  if (!shop) return null

  const endUser = await prisma.endUser.findUnique({
    where: { shopId_webVisitorId: { shopId: shop.id, webVisitorId: PLAYGROUND_WEB_VISITOR_ID } },
  })
  return { shop, endUser }
}

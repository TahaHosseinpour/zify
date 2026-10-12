import { NextRequest, NextResponse } from "next/server"
import { prisma, isChannelActive } from "@zify/db"

// Read by widget.js from the shop's own site, so it has to answer any origin.
// It says nothing that the shop's public storefront doesn't already.
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=60",
}

/** Whether this shop's site widget is switched on - the launcher only appears
 * when it is. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const shop = await prisma.shop.findUnique({ where: { slug }, select: { id: true, name: true } })
  if (!shop || !(await isChannelActive(shop.id, "widget"))) {
    return NextResponse.json({ active: false }, { headers: CORS })
  }
  return NextResponse.json({ active: true, name: shop.name }, { headers: CORS })
}

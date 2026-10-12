import { notFound } from "next/navigation"
import { prisma, isChannelActive } from "@zify/db"
import { WidgetChatClient } from "./widget-client"

export const dynamic = "force-dynamic"

/** The chat a shop embeds in its own site. widget.js (public/) loads this
 * page in an iframe; it is the storefront chat without the page around it. */
export default async function WidgetPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params

  const shop = await prisma.shop.findUnique({ where: { slug }, select: { id: true, name: true, welcomeMessage: true } })
  if (!shop) notFound()

  if (!(await isChannelActive(shop.id, "widget"))) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background p-6 text-center text-sm text-muted-foreground">
        دستیار این فروشگاه در حال حاضر فعال نیست.
      </div>
    )
  }

  return <WidgetChatClient slug={slug} shopName={shop.name} welcomeMessage={shop.welcomeMessage} />
}

import { notFound } from "next/navigation"
import { prisma } from "@zify/db"
import { ShopChatClient } from "./chat-client"

export const dynamic = "force-dynamic"

export default async function ShopChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ m?: string }>
}) {
  const { slug } = await params
  const { m } = await searchParams

  const shop = await prisma.shop.findUnique({ where: { slug }, select: { name: true, welcomeMessage: true } })
  if (!shop) notFound()

  return <ShopChatClient slug={slug} shopName={shop.name} welcomeMessage={shop.welcomeMessage} initialMessage={m ?? ""} />
}

import {
  embedFaq,
  embedProduct,
  embedShopInfoChunk,
  faqEmbedText,
  prisma,
  productEmbedText,
} from "@zify/db"

// The embedding calls themselves live in packages/db/src/embeddings.ts, shared
// with the backfill script: each save writes one vector per provider
// (`embedding` and `embedding_gemini`), so the agent can fall back to its
// second embedding provider.
export { embedFaq, embedProduct, embedShopInfoChunk }

/**
 * Re-generate embeddings for everything the agent retrieves for a shop:
 * all products, all FAQ items, and the shop-info chunks. Used by the
 * "Reset Agent" action so the assistant picks up edited catalog/FAQ data.
 */
export async function reembedAllForShop(shopId: string) {
  const [products, faqs] = await Promise.all([
    prisma.product.findMany({ where: { shopId } }),
    prisma.faqItem.findMany({ where: { shopId } }),
  ])

  for (const p of products) {
    const text = productEmbedText(p)
    if (text) await embedProduct(p.id, text)
  }

  for (const f of faqs) {
    await embedFaq(f.id, faqEmbedText(f))
  }

  await rebuildShopInfoChunks(shopId)

  return { products: products.length, faqs: faqs.length }
}

export async function rebuildShopInfoChunks(shopId: string) {
  const shop = await prisma.shop.findUnique({ where: { id: shopId } })
  if (!shop) return

  await prisma.shopInfoChunk.deleteMany({ where: { shopId } })

  const texts: string[] = []
  if (shop.description) texts.push(shop.description)
  if (shop.supportInfo) texts.push(JSON.stringify(shop.supportInfo))
  if (shop.systemPromptExtra) texts.push(shop.systemPromptExtra)

  for (const content of texts) {
    const chunk = await prisma.shopInfoChunk.create({
      data: { shopId, content },
    })
    await embedShopInfoChunk(chunk.id, content)
  }
}

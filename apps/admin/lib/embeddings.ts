import { prisma } from "@zify/db"

async function getEmbedding(text: string): Promise<number[]> {
  const baseUrl = (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/$/, "")
  const model = process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small"

  const res = await fetch(`${baseUrl}/embeddings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({ model, input: text }),
  })
  const data = await res.json()
  return data.data[0].embedding as number[]
}

function vectorToSql(vec: number[]): string {
  return `[${vec.join(",")}]`
}

export async function embedProduct(productId: string, text: string) {
  const embedding = await getEmbedding(text)
  await prisma.$executeRaw`
    UPDATE products SET embedding = ${vectorToSql(embedding)}::vector
    WHERE id = ${productId}
  `
}

export async function embedFaq(faqId: string, text: string) {
  const embedding = await getEmbedding(text)
  await prisma.$executeRaw`
    UPDATE faq_items SET embedding = ${vectorToSql(embedding)}::vector
    WHERE id = ${faqId}
  `
}

export async function embedShopInfoChunk(chunkId: string, text: string) {
  const embedding = await getEmbedding(text)
  await prisma.$executeRaw`
    UPDATE shop_info_chunks SET embedding = ${vectorToSql(embedding)}::vector
    WHERE id = ${chunkId}
  `
}

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
    const text = [p.name, p.description, p.category, p.brand].filter(Boolean).join(" ")
    if (text) await embedProduct(p.id, text)
  }

  for (const f of faqs) {
    // Embed the answer too: a customer's wording usually matches what the
    // answer says, not the way the question was phrased.
    await embedFaq(f.id, [f.question, f.answer].filter(Boolean).join(" "))
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

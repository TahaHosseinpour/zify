import { prisma } from "@zify/db"

// products/faq_items/shop_info_chunks.embedding are a fixed vector(1536)
// column (packages/db/prisma/schema.prisma), sized for OpenAI's
// text-embedding-3-small. Mirrors apps/agent/app/graph.py's EMBEDDING_DIM /
// _pad_to_dim — both write/read paths must pad to the same width, or a local
// model's shorter vectors would silently stop matching the ones written by
// this file (and vice versa). See that file's comment for why zero-padding
// leaves cosine distance exact rather than approximate.
const EMBEDDING_DIM = 1536

function localModelsEnabled(): boolean {
  const val = process.env.USE_LOCAL_MODELS
  return val != null && ["1", "true", "yes", "on"].includes(val.trim().toLowerCase())
}

function padToDim(vec: number[], dim = EMBEDDING_DIM): number[] {
  if (vec.length === dim) return vec
  if (vec.length > dim) {
    throw new Error(
      `embedding dim ${vec.length} exceeds the pgvector column width ${dim} — ` +
        "truncating would silently corrupt cosine distance; this model can't be " +
        "used against the current schema without a migration.",
    )
  }
  return [...vec, ...new Array(dim - vec.length).fill(0)]
}

async function getEmbedding(text: string): Promise<number[]> {
  // Same USE_LOCAL_MODELS switch as the agent (apps/agent/app/graph.py) —
  // kept in sync so a product embedded here and a customer query embedded by
  // the agent are always produced by the same model. Never set in
  // production; see deploy/templates/setup-env.sh.j2.
  const local = localModelsEnabled()
  const baseUrl = (
    local
      ? (process.env.OLLAMA_BASE_URL ?? "http://localhost:11434/v1")
      : (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1")
  ).replace(/\/$/, "")
  const model = local
    ? (process.env.OLLAMA_EMBEDDING_MODEL ?? "bge-m3")
    : (process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small")
  const apiKey = local ? "ollama" : process.env.OPENAI_API_KEY

  const res = await fetch(`${baseUrl}/embeddings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model, input: text }),
  })
  const data = await res.json()
  return padToDim(data.data[0].embedding as number[])
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

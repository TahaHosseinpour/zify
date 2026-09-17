/**
 * One-off local seed: adds a handful of realistic products (with real
 * embeddings) to the existing "starcoach" shop, so the storefront
 * (/shops/starcoach) and its chat have enough to actually show/recommend.
 * Not part of the automated `db:seed` pipeline - run manually:
 *
 *   bun prisma/seed-demo-products.ts
 */
import { prisma } from "../src/index"

async function getEmbedding(text: string): Promise<number[]> {
  const baseUrl = (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/$/, "")
  const model = process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small"

  const res = await fetch(`${baseUrl}/embeddings`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
    body: JSON.stringify({ model, input: text }),
  })
  const data = await res.json()
  return data.data[0].embedding as number[]
}

function vectorToSql(vec: number[]): string {
  return `[${vec.join(",")}]`
}

const DEMO_PRODUCTS = [
  {
    name: "بوت‌کمپ برنامه‌نویسی فرانت‌اند",
    price: 8_500_000,
    category: "تکنولوژی",
    brand: null,
    description: "دوره‌ی جامع React و Next.js از صفر تا استخدام، با پروژه‌ی واقعی و منتور اختصاصی.",
    imageUrl: "https://picsum.photos/seed/frontend/600/600",
    productUrl: "https://starcoach.example.com/courses/frontend-bootcamp",
  },
  {
    name: "دوره‌ی مهندسی پرامپت",
    price: 3_200_000,
    category: "هوش مصنوعی",
    brand: null,
    description: "یادگیری اصول نوشتن پرامپت حرفه‌ای برای مدل‌های زبانی و ساخت ایجنت‌های هوش مصنوعی.",
    imageUrl: "https://picsum.photos/seed/prompt/600/600",
    productUrl: "https://starcoach.example.com/courses/prompt-engineering",
  },
  {
    name: "بوت‌کمپ داده و یادگیری ماشین",
    price: 12_000_000,
    category: "هوش مصنوعی",
    brand: null,
    description: "از پایتون و پانداس تا مدل‌های یادگیری ماشین و استقرار در پروداکشن.",
    imageUrl: "https://picsum.photos/seed/ml/600/600",
    productUrl: "https://starcoach.example.com/courses/ml-bootcamp",
  },
  {
    name: "دوره‌ی توسعه بک‌اند با Node.js",
    price: 7_000_000,
    category: "تکنولوژی",
    brand: null,
    description: "طراحی API، دیتابیس، و معماری سرویس‌های مقیاس‌پذیر با Node.js و PostgreSQL.",
    imageUrl: "https://picsum.photos/seed/backend/600/600",
    productUrl: "https://starcoach.example.com/courses/backend-nodejs",
  },
  {
    name: "کارگاه ساخت ایجنت فروش با LangGraph",
    price: 4_500_000,
    category: "هوش مصنوعی",
    brand: null,
    description: "ساخت یک ایجنت مکالمه‌ای فروش از صفر، با LangGraph و پایگاه‌داده‌ی برداری.",
    imageUrl: "https://picsum.photos/seed/langgraph/600/600",
    productUrl: "https://starcoach.example.com/courses/agent-workshop",
  },
  {
    name: "دوره‌ی طراحی محصول دیجیتال",
    price: 5_800_000,
    category: "طراحی",
    brand: null,
    description: "از تحقیق کاربر تا طراحی رابط کاربری در Figma، برای محصولات نرم‌افزاری واقعی.",
    imageUrl: "https://picsum.photos/seed/uxui/600/600",
    productUrl: "https://starcoach.example.com/courses/product-design",
  },
]

async function main() {
  const shop = await prisma.shop.findUnique({ where: { slug: "starcoach" } })
  if (!shop) throw new Error('Shop with slug "starcoach" not found - run the main db:seed first.')

  for (const p of DEMO_PRODUCTS) {
    const product = await prisma.product.create({
      data: {
        shopId: shop.id,
        name: p.name,
        price: p.price,
        description: p.description,
        productUrl: p.productUrl,
        imageUrl: p.imageUrl,
        category: p.category,
        brand: p.brand,
      },
    })

    const embedText = [p.name, p.description, p.category, p.brand].filter(Boolean).join(" ")
    const embedding = await getEmbedding(embedText)
    await prisma.$executeRaw`
      UPDATE products SET embedding = ${vectorToSql(embedding)}::vector
      WHERE id = ${product.id}
    `
    console.log(`[seed-demo] product ready: ${product.name} (${product.id})`)
  }

  console.log(`[seed-demo] done - ${DEMO_PRODUCTS.length} products added to ${shop.name} (/shops/${shop.slug})`)
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })

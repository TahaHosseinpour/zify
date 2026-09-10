/**
 * One-off backfill for Product.category / Product.brand.
 *
 * The admin app never wrote these columns, so existing catalogs are almost
 * entirely NULL — which made the agent's SQL pre-filter match zero rows on
 * every search and silently fall back to price-only filtering. This asks the
 * model to label each product from its name and description, constrained to a
 * vocabulary derived from the shop itself so the values stay consistent.
 *
 *   bun packages/db/prisma/backfill-categories.ts [--shop <id>] [--dry-run]
 *
 * Safe to re-run: only products with a NULL/empty category are touched.
 */
import { PrismaClient } from "@prisma/client"

const prisma = new PrismaClient()

const OPENAI_BASE_URL = process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1"
const MODEL = process.env.OPENAI_CHAT_MODEL ?? "gpt-4o-mini"
const BATCH = 20

interface Labelled {
  id: string
  category: string
  brand: string | null
}

async function labelBatch(
  products: { id: string; name: string; description: string | null }[],
  vocabulary: string[],
): Promise<Labelled[]> {
  const vocabLine = vocabulary.length
    ? `دسته‌بندی هر محصول را ترجیحاً از این فهرست انتخاب کن: ${vocabulary.join("، ")}.\n` +
      `اگر هیچ‌کدام مناسب نبود، یک دسته‌ی تازه بساز که **نوع خود محصول** را بگوید.`
    : `برای هر محصول یک دسته‌بندی بنویس که نوع خود محصول را بگوید.`

  const list = products
    .map((p) => `${p.id} :: ${p.name} :: ${p.description ?? ""}`)
    .join("\n")

  const res = await fetch(`${OPENAI_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: MODEL,
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "user",
          content:
            `${vocabLine}\n` +
            `دسته باید کوتاه باشد و همان کلمه‌ای که مشتری به کار می‌برد (مثل «لپ تاپ»، ` +
            `«گوشی»، «پاوربانک»، «هدفون»). دسته‌های یکسان را عیناً با همان املا تکرار کن.\n` +
            `⚠️ هرگز برچسب‌های بی‌معنا مثل «عمومی»، «متفرقه» یا «سایر» نساز — ` +
            `دسته باید نوع واقعی کالا را بگوید.\n\n` +
            `برند را فقط وقتی بنویس که در نام محصول آمده باشد، وگرنه null.\n\n` +
            `محصولات (شناسه :: نام :: توضیحات):\n${list}\n\n` +
            `خروجی دقیقاً به این شکل JSON بده:\n` +
            `{"items":[{"id":"...","category":"...","brand":"..." یا null}]}`,
        },
      ],
    }),
  })

  if (!res.ok) throw new Error(`OpenAI responded ${res.status}: ${await res.text()}`)
  const data = await res.json()
  const parsed = JSON.parse(data.choices[0].message.content)
  return parsed.items ?? []
}

async function main() {
  const args = process.argv.slice(2)
  const dryRun = args.includes("--dry-run")
  const shopArg = args.indexOf("--shop")
  const shopFilter = shopArg !== -1 ? args[shopArg + 1] : null

  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is not set")
  }

  const shops = await prisma.shop.findMany({
    where: shopFilter ? { id: shopFilter } : undefined,
    select: { id: true, name: true },
  })

  for (const shop of shops) {
    const pending = await prisma.product.findMany({
      where: { shopId: shop.id, OR: [{ category: null }, { category: "" }] },
      select: { id: true, name: true, description: true },
    })
    if (pending.length === 0) {
      console.log(`[${shop.name}] nothing to backfill`)
      continue
    }

    // Seed the vocabulary from categories this shop already uses, so a partial
    // backfill stays consistent with whatever was labelled before.
    const existing = await prisma.product.findMany({
      where: { shopId: shop.id, NOT: { category: null } },
      select: { category: true },
      distinct: ["category"],
    })
    const vocabulary = existing
      .map((r) => r.category)
      .filter((c): c is string => Boolean(c))

    console.log(
      `[${shop.name}] ${pending.length} products, vocabulary: ${
        vocabulary.length ? vocabulary.join("، ") : "(empty — will be derived)"
      }`,
    )

    for (let i = 0; i < pending.length; i += BATCH) {
      const chunk = pending.slice(i, i + BATCH)
      const labelled = await labelBatch(chunk, vocabulary)

      for (const item of labelled) {
        if (!item.category) continue
        const category = item.category.trim()
        const brand = item.brand?.trim() || null
        console.log(`  ${category}${brand ? ` / ${brand}` : ""}  ←  ${
          chunk.find((p) => p.id === item.id)?.name ?? item.id
        }`)
        if (!dryRun) {
          await prisma.product.update({
            where: { id: item.id },
            data: { category, brand },
          })
        }
        if (!vocabulary.includes(category)) vocabulary.push(category)
      }
    }

    if (!dryRun) {
      // Keep the shop-level list in step with what the products actually say;
      // it is what the admin UI offers as autocomplete.
      await prisma.shop.update({
        where: { id: shop.id },
        data: { categories: vocabulary },
      })
    }
  }

  console.log(dryRun ? "\ndry run — nothing written" : "\ndone")
  console.log("Re-index embeddings afterwards: dashboard → تنظیمات → ریست حافظه دستیار")
}

main()
  .catch((err) => {
    console.error(err)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())

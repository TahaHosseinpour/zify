/**
 * Bulk-imports a demo product catalog from a CSV file into an existing shop,
 * computing a real embedding for each product exactly like
 * prisma/seed-demo-products.ts does - so the new products are immediately
 * searchable by the agent's vector_search_* nodes, not just visible in the
 * admin panel.
 *
 * CSV columns (header row required, in this order or any order - matched by
 * name): name, price, category, brand, description, imageUrl, productUrl,
 * stock, isActive
 *
 * Usage:
 *   bun prisma/import-csv-products.ts <shopSlug> <path-to-csv>
 *
 * Example:
 *   bun prisma/import-csv-products.ts starcoach zify-demo-products-100.csv
 */
import { readFileSync } from "fs"
import { prisma } from "../src/index"

// ---- minimal RFC4180 CSV parser (handles quoted fields, embedded commas/quotes) ----
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ""
  let inQuotes = false
  // Strip a UTF-8 BOM if present (Excel/Python csv writers add one).
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1)

  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else {
          inQuotes = false
        }
      } else {
        field += c
      }
    } else if (c === '"') {
      inQuotes = true
    } else if (c === ",") {
      row.push(field)
      field = ""
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++
      row.push(field)
      field = ""
      if (row.some((f) => f.length > 0) || row.length > 1) rows.push(row)
      row = []
    } else {
      field += c
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field)
    rows.push(row)
  }

  const header = rows[0]
  return rows.slice(1).map((r) => {
    const obj: Record<string, string> = {}
    header.forEach((h, idx) => (obj[h.trim()] = (r[idx] ?? "").trim()))
    return obj
  })
}

// ---- embedding (same as seed-demo-products.ts) ----
async function getEmbedding(text: string): Promise<number[]> {
  const baseUrl = (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/$/, "")
  const model = process.env.OPENAI_EMBEDDING_MODEL ?? "text-embedding-3-small"

  const res = await fetch(`${baseUrl}/embeddings`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
    body: JSON.stringify({ model, input: text }),
  })
  if (!res.ok) {
    throw new Error(`embeddings request failed: ${res.status} ${await res.text()}`)
  }
  const data = await res.json()
  return data.data[0].embedding as number[]
}

function vectorToSql(vec: number[]): string {
  return `[${vec.join(",")}]`
}

function toBool(v: string, fallback = true): boolean {
  if (v === undefined || v === "") return fallback
  return ["true", "1", "yes", "y"].includes(v.toLowerCase())
}

async function main() {
  const [shopSlug, csvPath] = process.argv.slice(2)
  if (!shopSlug || !csvPath) {
    console.error("usage: bun prisma/import-csv-products.ts <shopSlug> <path-to-csv>")
    process.exit(1)
  }

  const shop = await prisma.shop.findUnique({ where: { slug: shopSlug } })
  if (!shop) throw new Error(`Shop with slug "${shopSlug}" not found.`)

  const csvText = readFileSync(csvPath, "utf-8")
  const records = parseCsv(csvText)
  console.log(`[import-csv] parsed ${records.length} rows from ${csvPath}`)

  let ok = 0
  let failed = 0
  for (const rec of records) {
    try {
      const name = rec.name
      const price = Number(rec.price)
      const category = rec.category || null
      const brand = rec.brand || null
      const description = rec.description || null
      const imageUrl = rec.imageUrl || null
      const productUrl = rec.productUrl || null
      const stock = rec.stock ? Number(rec.stock) : 0
      const isActive = toBool(rec.isActive, true)

      if (!name || Number.isNaN(price)) {
        console.warn(`[import-csv] skipping row with invalid name/price:`, rec)
        failed++
        continue
      }

      const product = await prisma.product.create({
        data: {
          shopId: shop.id,
          name,
          price,
          description,
          productUrl,
          imageUrl,
          category,
          brand,
          stock,
          isActive,
        },
      })

      const embedText = [name, description, category, brand].filter(Boolean).join(" ")
      const embedding = await getEmbedding(embedText)
      await prisma.$executeRaw`
        UPDATE products SET embedding = ${vectorToSql(embedding)}::vector
        WHERE id = ${product.id}
      `
      ok++
      if (ok % 10 === 0) console.log(`[import-csv] ${ok}/${records.length} imported...`)
    } catch (err) {
      failed++
      console.error(`[import-csv] failed on row`, rec.name, err)
    }
  }

  console.log(`[import-csv] done - ${ok} imported, ${failed} failed, into ${shop.name} (/shops/${shop.slug})`)
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })

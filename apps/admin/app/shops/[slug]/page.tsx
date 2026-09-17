import { notFound } from "next/navigation"
import Image from "next/image"
import { prisma } from "@zify/db"
import { ProductCard } from "@/components/shop-chat/product-card"
import { HeroChatInput } from "./hero-chat-input"

export const dynamic = "force-dynamic"

async function getShopWithProducts(slug: string) {
  const shop = await prisma.shop.findUnique({ where: { slug } })
  if (!shop) return null

  const products = await prisma.product.findMany({
    where: { shopId: shop.id, isActive: true },
    orderBy: { createdAt: "desc" },
  })

  return { shop, products }
}

export default async function ShopStorefrontPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const data = await getShopWithProducts(slug)
  if (!data) notFound()
  const { shop, products } = data

  const byCategory = new Map<string, typeof products>()
  for (const product of products) {
    const key = product.category?.trim() || "سایر"
    if (!byCategory.has(key)) byCategory.set(key, [])
    byCategory.get(key)!.push(product)
  }

  return (
    <div className="min-h-screen bg-background text-foreground" dir="rtl">
      {/* Hero */}
      <section className="flex flex-col items-center gap-6 px-4 py-16 text-center">
        {shop.logoUrl && (
          <Image
            src={shop.logoUrl}
            alt={shop.name}
            width={72}
            height={72}
            className="rounded-2xl object-cover"
            unoptimized
          />
        )}
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold">{shop.name}</h1>
          {shop.description && <p className="max-w-md text-sm text-muted-foreground">{shop.description}</p>}
        </div>
        <HeroChatInput slug={slug} />
      </section>

      {/* Product showcase */}
      <section className="mx-auto flex max-w-6xl flex-col gap-10 px-4 pb-20">
        {products.length === 0 ? (
          <p className="py-16 text-center text-muted-foreground">هنوز محصولی ثبت نشده است</p>
        ) : (
          Array.from(byCategory.entries()).map(([category, items]) => (
            <div key={category} className="flex flex-col gap-4">
              <h2 className="text-lg font-semibold">{category}</h2>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {items.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={{
                      id: product.id,
                      name: product.name,
                      price: product.price.toNumber(),
                      imageUrl: product.imageUrl,
                      productUrl: product.productUrl,
                    }}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

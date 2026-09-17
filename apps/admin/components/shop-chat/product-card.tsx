import Image from "next/image"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { ShoppingCart01Icon } from "@hugeicons/core-free-icons"

export interface DisplayProduct {
  id: string
  name: string
  price: number | string | null
  imageUrl: string | null
  productUrl: string | null
}

export function ProductCard({ product, onDetails }: { product: DisplayProduct; onDetails?: () => void }) {
  const price = product.price != null ? Number(product.price) : null
  return (
    <Card className="overflow-hidden py-0">
      <div className="relative aspect-square w-full bg-muted">
        {product.imageUrl ? (
          <Image src={product.imageUrl} alt={product.name} fill className="object-cover" unoptimized />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">بدون تصویر</div>
        )}
      </div>
      <CardContent className="flex flex-col gap-2 p-3">
        <p className="line-clamp-2 text-sm font-medium">{product.name}</p>
        {price != null && (
          <p className="text-sm font-semibold text-primary">{price.toLocaleString("fa-IR")} تومان</p>
        )}
        <div className="flex gap-2">
          {onDetails && (
            <Button variant="outline" size="sm" className="flex-1" onClick={onDetails}>
              اطلاعات بیشتر
            </Button>
          )}
          {product.productUrl && (
            <Button asChild size="sm" className="flex-1 gap-1.5">
              <a href={product.productUrl} target="_blank" rel="noopener noreferrer">
                <HugeiconsIcon icon={ShoppingCart01Icon} className="size-4" />
                خرید
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

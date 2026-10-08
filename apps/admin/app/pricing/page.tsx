import type { Metadata } from "next"
import { prisma } from "@zify/db"
import Navbar from "@/components/landing/Navbar"
import Footer from "@/components/landing/Footer"
import PricingSection from "@/components/landing/PricingSection"

export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "پلن‌ها و قیمت | زیفای",
  description: "پلن‌های اشتراک دستیار فروش زیفای برای کسب‌وکارهای کوچک و بزرگ",
}

export default async function PricingPage() {
  const plans = await prisma.plan.findMany({
    where: { isActive: true },
    orderBy: { sortOrder: "asc" },
  })

  return (
    <div className="min-h-screen bg-background" dir="rtl">
      <Navbar />
      {/* The navbar is glass with white text, built to sit on the landing
          page's dark hero - this band gives it the same ground here. */}
      <header className="bg-[#0a0a0a] px-4 pb-14 pt-32 text-center sm:px-6">
        <h1 className="text-3xl font-black text-white sm:text-4xl">پلن‌ها و قیمت</h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-white/60">
          هزینه بر اساس تعداد گفتگوی مشتریان شما با دستیار است. پلن را انتخاب کنید و درخواست بدهید؛ برای هماهنگی و
          فعال‌سازی با شما تماس می‌گیریم.
        </p>
      </header>
      <main>
        <PricingSection
          plans={plans.map((p) => ({
            key: p.key,
            name: p.name,
            description: p.description,
            conversationsPerMonth: p.conversationsPerMonth,
            monthlyPriceToman: p.monthlyPriceToman,
            discountPercent3Months: p.discountPercent3Months,
            discountPercent12Months: p.discountPercent12Months,
            maxActiveProducts: p.maxActiveProducts,
            maxFaqItems: p.maxFaqItems,
            maxBroadcastsPerMonth: p.maxBroadcastsPerMonth,
          }))}
        />
      </main>
      <Footer />
    </div>
  )
}

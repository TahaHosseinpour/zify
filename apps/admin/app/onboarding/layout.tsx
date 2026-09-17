import { redirect } from "next/navigation"
import { getSession } from "@/lib/auth"
import { prisma } from "@zify/db"

export default async function OnboardingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getSession()
  if (!session) redirect("/login")

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { shops: true },
  })

  if (!user) redirect("/login")
  // Mirrors dashboard/layout.tsx's own redirect the other way - once either
  // signal is true the wizard is done, so re-visiting this URL (a bookmark,
  // browser back, a stale link) sent people straight back into step 1
  // instead of the dashboard, and re-submitting it there failed with "این
  // شناسه قبلاً استفاده شده است" since /api/shop always tries to create a
  // new shop rather than checking for an existing one.
  if (user.onboardingCompleted || user.shops.length > 0) {
    redirect("/dashboard")
  }

  return <>{children}</>
}

import { AppSidebar } from "@/components/app-sidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { getSession } from "@/lib/auth"
import { redirect } from "next/navigation"
import { prisma } from "@zify/db"

export default async function DashboardLayout({
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
  if (!user.onboardingCompleted && user.shops.length === 0) {
    redirect("/onboarding")
  }

  const shop = user.shops[0]

  return (
    <SidebarProvider>
      <AppSidebar side="right" shopName={shop?.name} userMobile={user.mobile} />
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="me-2" />
          <Separator orientation="vertical" className="h-4" />
        </header>
        <div className="flex flex-1 flex-col gap-4 p-4">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  )
}

import { AppSidebar } from "@/components/app-sidebar"
import { PanelHeader } from "@/components/panel-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
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
    <SidebarProvider className="panel-theme bg-background">
      <AppSidebar side="right" shopName={shop?.name} userMobile={user.mobile} />
      <SidebarInset>
        <PanelHeader />
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 p-4 sm:p-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

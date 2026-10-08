import { redirect } from "next/navigation"
import { AppSidebar } from "@/components/app-sidebar"
import { PanelHeader } from "@/components/panel-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { getAdmin } from "@/lib/admin-auth"
import { adminNavGroups } from "@/lib/nav"

export const dynamic = "force-dynamic"

/** The platform admin panel. Everything in this route group requires an admin
 * session (lib/admin-auth.ts); /admin/login sits outside the group so it can
 * be reached without one. A shop owner's session counts for nothing here. */
export default async function AdminPanelLayout({ children }: { children: React.ReactNode }) {
  const admin = await getAdmin()
  if (!admin) redirect("/admin/login")

  return (
    <SidebarProvider className="panel-theme bg-background">
      <AppSidebar
        side="right"
        shopName="مدیریت پلتفرم"
        accountLabel={admin.fullName ?? admin.username}
        groups={adminNavGroups}
        homeHref="/admin"
        logoutEndpoint="/api/admin/auth/logout"
        afterLogoutHref="/admin/login"
      />
      <SidebarInset>
        <PanelHeader />
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 p-4 sm:p-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

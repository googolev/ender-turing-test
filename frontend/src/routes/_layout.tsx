import {
  createFileRoute,
  Outlet,
  redirect,
  useRouter,
} from "@tanstack/react-router"
import { useEffect, useRef } from "react"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

// The current user is refetched when the tab regains focus. If an admin changed
// their role meanwhile, re-run the route guards so a page they lost access to
// is left right away instead of on the next request that happens to get a 403.
function useGuardsFollowPermissions() {
  const { user } = useAuth()
  const router = useRouter()
  const permissions = user?.permissions.join(" ")
  const previous = useRef(permissions)

  useEffect(() => {
    if (previous.current !== undefined && permissions !== previous.current) {
      router.invalidate()
    }
    previous.current = permissions
  }, [permissions, router])
}

function Layout() {
  useGuardsFollowPermissions()

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b bg-background px-4">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
        </header>
        <main className="flex-1 p-6 md:p-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}

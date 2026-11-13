import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"

import { MetricsService } from "@/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { requirePermission } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/metrics")({
  component: Metrics,
  beforeLoad: () => requirePermission("metrics:read"),
  head: () => ({
    meta: [
      {
        title: "Metrics - FastAPI Template",
      },
    ],
  }),
})

function MetricsCards() {
  const { data: metrics } = useSuspenseQuery({
    queryKey: ["metrics"],
    queryFn: async () => (await MetricsService.readMetrics()).data,
  })

  const cards = [
    { title: "Total users", value: metrics.users_total },
    { title: "Active users", value: metrics.users_active },
    { title: "Admins", value: metrics.users_by_role.admin ?? 0 },
    { title: "Managers", value: metrics.users_by_role.manager ?? 0 },
    { title: "Members", value: metrics.users_by_role.member ?? 0 },
    { title: "Items", value: metrics.items_total },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map(({ title, value }) => (
        <Card key={title}>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function Metrics() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
        <p className="text-muted-foreground">Basic usage numbers</p>
      </div>
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <MetricsCards />
      </Suspense>
    </div>
  )
}

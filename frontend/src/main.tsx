import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { client } from "./client/client.gen"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  auth: () => localStorage.getItem("access_token") || "",
})

const handleApiError = (error: Error) => {
  if (!(error instanceof AxiosError)) return
  const status = error.response?.status
  if (status === 401) {
    // The session is gone: bad or expired token, or the user was deactivated or deleted.
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  } else if (status === 403) {
    // Access denied, but the session is still valid. The user's access may have
    // changed, so refresh the current user and re-run the route guards.
    queryClient.invalidateQueries({ queryKey: ["currentUser"] })
    router.invalidate()
  }
}
// Retrying a 4xx cannot change the answer; it only delays the reaction to a lost
// session (401) or changed access (403). Network errors and 5xx still retry.
const isClientError = (error: Error) => {
  const status =
    error instanceof AxiosError ? error.response?.status : undefined
  return status !== undefined && status >= 400 && status < 500
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => !isClientError(error) && failureCount < 3,
    },
  },
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)

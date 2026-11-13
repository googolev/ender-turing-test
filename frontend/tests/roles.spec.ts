import {
  type APIRequestContext,
  expect,
  type Page,
  test,
} from "@playwright/test"
import { randomEmail, randomPassword } from "./utils/random.ts"
import {
  createUserAsAdmin,
  logInUser,
  updateUserAsAdmin,
} from "./utils/user.ts"

// Every test logs in as a fresh user with the role under test.
test.use({ storageState: { cookies: [], origins: [] } })

type Role = "admin" | "manager" | "member"

async function logInAs(page: Page, request: APIRequestContext, role: Role) {
  const email = randomEmail()
  const password = randomPassword()
  const user = await createUserAsAdmin(request, { email, password, role })
  await logInUser(page, email, password)
  return user
}

const navLink = (page: Page, name: string) =>
  page.getByRole("link", { name, exact: true })

async function openUsersPage(page: Page, ownEmail: string) {
  await navLink(page, "Users").click()
  await page.waitForURL("/admin")
  // Wait for the table so the absence checks below are meaningful.
  await expect(
    page.getByRole("row").filter({ hasText: ownEmail }),
  ).toBeVisible()
}

test("Member sees no user or metrics pages and is redirected from their URLs", async ({
  page,
  request,
}) => {
  await logInAs(page, request, "member")

  await expect(navLink(page, "Items")).toBeVisible()
  await expect(navLink(page, "Users")).toHaveCount(0)
  await expect(navLink(page, "Metrics")).toHaveCount(0)

  for (const path of ["/admin", "/metrics"]) {
    await page.goto(path)
    await page.waitForURL("/")
    await expect(
      page.getByText("Welcome back, nice to see you again!"),
    ).toBeVisible()
  }
})

test("Manager can view users and metrics but not manage users", async ({
  page,
  request,
}) => {
  const manager = await logInAs(page, request, "manager")

  await openUsersPage(page, manager.email)
  await expect(page.getByRole("button", { name: "Add User" })).toHaveCount(0)
  await expect(page.getByRole("row").getByRole("button")).toHaveCount(0)

  await navLink(page, "Metrics").click()
  await page.waitForURL("/metrics")
  await expect(page.getByText("Total users")).toBeVisible()
})

test("Admin can manage users and view metrics", async ({ page, request }) => {
  const admin = await logInAs(page, request, "admin")

  await openUsersPage(page, admin.email)
  await expect(page.getByRole("button", { name: "Add User" })).toBeVisible()
  // Other users' rows have an actions menu; the admin's own row does not.
  await expect(page.getByRole("row").getByRole("button").first()).toBeVisible()
  await expect(
    page.getByRole("row").filter({ hasText: admin.email }).getByRole("button"),
  ).toHaveCount(0)

  await navLink(page, "Metrics").click()
  await page.waitForURL("/metrics")
  await expect(page.getByText("Total users")).toBeVisible()
})

test("Admin has no danger zone in settings", async ({ page, request }) => {
  await logInAs(page, request, "admin")
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Danger zone" })).toHaveCount(0)
})

test("Manager demoted during a session stays logged in and loses user pages", async ({
  page,
  request,
}) => {
  const manager = await logInAs(page, request, "manager")
  await openUsersPage(page, manager.email)

  await updateUserAsAdmin(request, manager.id, { role: "member" })
  // The user comes back to the tab: the current user is refetched, the
  // permissions changed, so the route guards run again.
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")))

  await page.waitForURL("/")
  await expect(
    page.getByText("Welcome back, nice to see you again!"),
  ).toBeVisible()
  await expect(navLink(page, "Users")).toHaveCount(0)
  await expect(navLink(page, "Metrics")).toHaveCount(0)
})

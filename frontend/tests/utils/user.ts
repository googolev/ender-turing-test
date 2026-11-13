import { type APIRequestContext, expect, type Page } from "@playwright/test"
import { firstSuperuser, firstSuperuserPassword } from "../config.ts"

const apiUrl = `${process.env.VITE_API_URL}/api/v1`

export async function setUserActive(
  request: APIRequestContext,
  userId: string,
  isActive: boolean,
) {
  const login = await request.post(`${apiUrl}/login/access-token`, {
    form: { username: firstSuperuser, password: firstSuperuserPassword },
  })
  expect(login.ok()).toBeTruthy()
  const { access_token } = await login.json()
  const response = await request.patch(`${apiUrl}/users/${userId}`, {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { is_active: isActive },
  })
  expect(response.ok()).toBeTruthy()
}

export async function signUpNewUser(
  page: Page,
  name: string,
  email: string,
  password: string,
) {
  await page.goto("/signup")

  await page.getByTestId("full-name-input").fill(name)
  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByTestId("confirm-password-input").fill(password)
  await page.getByRole("button", { name: "Sign Up" }).click()
  await page.goto("/login")
}

export async function logInUser(page: Page, email: string, password: string) {
  await page.goto("/login")

  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByRole("button", { name: "Log In" }).click()
  await page.waitForURL("/")
  await expect(
    page.getByText("Welcome back, nice to see you again!"),
  ).toBeVisible()
}

export async function logOutUser(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByRole("menuitem", { name: "Log out" }).click()
  await page.goto("/login")
}

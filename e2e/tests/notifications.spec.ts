import { expect, type Page, test } from '@playwright/test'

// TC-99-09: a signed-in user sees their private inbox section with its empty state.
// Trigger stories (SCRUM-96/102/95/94) extend this flow with real notifications.
test.describe.configure({ retries: 0 })

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test('a signed-in user sees their private notification inbox', async ({ page }) => {
  await signIn(page, 'organiser@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  const inbox = page.getByRole('region', { name: 'Notifications', exact: true })
  await expect(inbox).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Notifications', level: 1 })).toBeVisible()
})

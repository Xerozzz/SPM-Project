import { expect, type Page, test } from '@playwright/test'

// SCRUM-104: the Coordinator can reach the end of their work without scrolling
// the outer page into blank space. In particular, positioned field labels must
// stay inside the workspace's scroll boundary.
async function openReviewQueue(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill('coordinator@example.com')
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Review Queue', exact: true })).toBeVisible()
  await expect(
    page.locator('main > section:not([hidden]) > section > article').first(),
  ).toBeAttached()
  await page.waitForLoadState('networkidle')
}

test('desktop scrolling stops at the last review card without moving the outer page', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openReviewQueue(page)
  const workspace = page.locator('main').locator('..').locator('..')
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBe(900)
  await workspace.evaluate((element) => {
    element.scrollTop = element.scrollHeight
  })
  await expect(
    page.locator('main > section:not([hidden]) > section > article').last(),
  ).toBeInViewport()
  const bottom = await workspace.evaluate((element) => element.scrollTop)

  await page.mouse.move(1000, 700)
  await page.mouse.wheel(0, 2000)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  expect(await workspace.evaluate((element) => element.scrollTop)).toBe(bottom)
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeInViewport()
})

test('mobile review content remains scrollable to its last card', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await openReviewQueue(page)
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await expect(
    page.locator('main > section:not([hidden]) > section > article').last(),
  ).toBeInViewport()
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0)
})

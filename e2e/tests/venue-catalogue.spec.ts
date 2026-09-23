import { expect, type Page, test } from '@playwright/test'

// SCRUM-59: reading the venue catalogue in the browser.
//
// Relies on the dev seed (scripts/seed.py), which the api container runs on every start:
// three venues, one of them ("Old Sports Hall") deactivated, so AC3 and AC4 are both
// visible without this test having to change anything.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Venue catalogue' })).toBeVisible()
}

function section(page: Page) {
  return page.getByRole('heading', { name: 'Venue catalogue' }).locator('xpath=..')
}

test('a coordinator reads the catalogue and cannot change it (AC2)', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  await expect(
    section(page).getByRole('listitem').filter({ hasText: 'Mochtar Riady Auditorium' }),
  ).toContainText('up to 500 people')
  // AC2: nothing in the catalogue creates, edits or deactivates a venue.
  await expect(section(page).getByRole('button')).toHaveCount(0)
})

test('a deactivated venue is not offered for planning (AC3)', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  await expect(
    section(page).getByRole('listitem').filter({ hasText: 'Old Sports Hall' }),
  ).toHaveCount(0)
})

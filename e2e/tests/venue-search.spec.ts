import { expect, type Page, test } from '@playwright/test'

// SCRUM-55: an Event Coordinator searches for venues with planning filters.
//
// TDD red phase: the venue-search UI does not exist yet, so both tests fail until it
// lands. Expected UI contract (to be built):
//   - A "Venue search" section visible to coordinators with labelled inputs:
//     Date, Start time, End time, Minimum capacity, Location, Accessibility needs,
//     Facilities, Room layout, and a "Search venues" button.
//   - Results render as a list; each matching venue name is visible.
//   - TC-55-AC7-01: when nothing matches, the results area states no match was found
//     and suggests adjusting filters.
// Relies on the dev seed (scripts/seed.py) for the signed-in coordinator account.

async function signInAsCoordinator(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('coordinator@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Venue search' })).toBeVisible()
}

test('TC-55-AC1-01: a coordinator can provide every supported search criterion', async ({
  page,
}) => {
  await signInAsCoordinator(page)

  await page.getByLabel('Date').fill('2026-12-01')
  await page.getByLabel('Start time').fill('10:00')
  await page.getByLabel('End time').fill('12:00')
  await page.getByLabel('Minimum capacity').fill('100')
  await page.getByLabel('Location').fill('Level 2, School of Computing')
  await page.getByLabel('Accessibility needs').fill('Step-free access')
  await page.getByLabel('Facilities').fill('Projector')
  await page.getByLabel('Room layout').selectOption('theatre')
  await page.getByRole('button', { name: 'Search venues' }).click()

  // The system accepts every criterion and shows Hall A in the results.
  await expect(page.getByRole('listitem').filter({ hasText: 'Hall A' })).toBeVisible()
})

test('TC-55-AC7-01: no-match guidance suggests adjusting filters', async ({ page }) => {
  await signInAsCoordinator(page)

  await page.getByLabel('Date').fill('2026-12-01')
  await page.getByLabel('Start time').fill('10:00')
  await page.getByLabel('End time').fill('12:00')
  await page.getByLabel('Minimum capacity').fill('999')
  await page.getByRole('button', { name: 'Search venues' }).click()

  await expect(page.getByText(/no .* venue .* found/i)).toBeVisible()
  await expect(page.getByText(/adjust.*filter/i)).toBeVisible()
})

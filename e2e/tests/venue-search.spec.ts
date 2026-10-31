import { expect, type Page, test } from '@playwright/test'

// SCRUM-55: an Event Coordinator searches for venues with planning filters.
//
// Multi-day requested periods (1 Dec 2026 10:00 through 3 Dec 2026 12:00).
// Expected UI contract:
//   - A "Venue search" section visible to coordinators with labelled inputs:
//     Start date, Start time, End date, End time, Minimum capacity, Location,
//     Accessibility needs, Facilities, Room layout, and a "Search venues" button.
//   - Results render as a list; each matching venue name is visible.
//   - TC-55-AC7-01: when nothing matches, the results area states no match was found
//     and suggests adjusting filters.
// Relies on the dev seed (scripts/seed.py) for the signed-in coordinator account.

async function signInAsCoordinator(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('coordinator@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Venue Planning', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Venue search', exact: true })).toBeVisible()
}

/**
 * Two dates a little way ahead, in Singapore time, because the search form's fields are read
 * as Singapore wall clock and the API now refuses a period that has already ended. The dates
 * used to be hardcoded as December 2026; that was harmless while a past period merely
 * returned nothing, and became a guaranteed failure of both specs the moment it started
 * answering 422.
 */
function daysAhead(days: number): string {
  const sgt = new Date(Date.now() + 8 * 60 * 60 * 1000 + days * 24 * 60 * 60 * 1000)
  return sgt.toISOString().slice(0, 10)
}

const START_DATE = daysAhead(30)
const END_DATE = daysAhead(32)

test('TC-55-AC1-01: a coordinator can provide every supported search criterion', async ({
  page,
}) => {
  await signInAsCoordinator(page)
  const venueSearch = page.getByRole('region', { name: 'Venue search', exact: true })

  await venueSearch.getByLabel('Start date', { exact: true }).fill(START_DATE)
  await venueSearch.getByLabel('Start time', { exact: true }).fill('10:00')
  await venueSearch.getByLabel('End date', { exact: true }).fill(END_DATE)
  await venueSearch.getByLabel('End time', { exact: true }).fill('12:00')
  await venueSearch.getByLabel('Minimum capacity', { exact: true }).fill('100')
  await venueSearch.getByLabel('Location', { exact: true }).fill('Level 2, School of Computing')
  await venueSearch.getByLabel('Accessibility needs', { exact: true }).fill('Step-free access')
  await venueSearch.getByLabel('Facilities', { exact: true }).fill('Projector')
  await venueSearch
    .getByRole('combobox', { name: 'Room layout', exact: true })
    .selectOption('theatre')
  await page.getByRole('button', { name: 'Search venues' }).click()

  // Scope the assertion to search results so Hall A in the venue catalogue cannot satisfy it.
  await expect(venueSearch.getByRole('listitem').filter({ hasText: /^Hall A ·/ })).toBeVisible()
})

test('TC-55-AC7-01: no-match guidance suggests adjusting filters', async ({ page }) => {
  await signInAsCoordinator(page)
  const venueSearch = page.getByRole('region', { name: 'Venue search', exact: true })

  await venueSearch.getByLabel('Start date', { exact: true }).fill(START_DATE)
  await venueSearch.getByLabel('Start time', { exact: true }).fill('10:00')
  await venueSearch.getByLabel('End date', { exact: true }).fill(END_DATE)
  await venueSearch.getByLabel('End time', { exact: true }).fill('12:00')
  await venueSearch.getByLabel('Minimum capacity', { exact: true }).fill('999')
  await page.getByRole('button', { name: 'Search venues' }).click()

  await expect(page.getByText(/no .* venue .* found/i)).toBeVisible()
  await expect(page.getByText(/adjust.*filter/i)).toBeVisible()
})

import { expect, type Page, test } from '@playwright/test'

// SCRUM-59: the venue catalogue through the browser.
//
// Relies on the dev seed (scripts/seed.py), which the api container runs on every start:
// three venues, one of them ("Old Sports Hall") deactivated on purpose so AC3 and AC4 are
// both visible without this test having to deactivate anything first.
//
// The venue this test adds is named with a timestamp so the file can be re-run against the
// same database. Venue names are unique and deactivation is not a delete (ADR-0012), so a
// fixed name would collide with the row left by the previous run.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Venue catalogue' })).toBeVisible()
}

function catalogue(page: Page) {
  return page
    .getByRole('heading', { name: 'Venue catalogue' })
    .locator('xpath=..')
    .getByRole('listitem')
}

test('venue staff add a venue and take it out of use (AC1, AC3)', async ({ page }) => {
  const name = `E2E Hall ${Date.now()}`
  await signIn(page, 'venue-staff@example.com')

  await page.getByLabel(/^Name/).fill(name)
  await page.getByLabel(/^Location/).fill('Level 4, Campus Green')
  await page.getByLabel(/^Maximum capacity/).fill('120')
  await page.getByLabel('classroom').check()
  await page.getByLabel(/^Opens at/).fill('09:00')
  await page.getByLabel(/^Closes at/).fill('18:00')
  await page.getByRole('button', { name: 'Add venue' }).click()

  // Home also has a role="status" line for API health, so pick ours by its text.
  await expect(page.getByRole('status').filter({ hasText: name })).toContainText(
    `“${name}” has been added to the catalogue.`,
  )
  const added = catalogue(page).filter({ hasText: name })
  await expect(added).toContainText('up to 120 people')
  await expect(added).toContainText('09:00 to 18:00')

  // AC3: deactivating takes it out of the selectable catalogue, without deleting it.
  await added.getByRole('button', { name: 'Deactivate' }).click()
  await expect(page.getByRole('status').filter({ hasText: name })).toContainText(
    `“${name}” has been deactivated and can no longer be selected.`,
  )
  await expect(catalogue(page).filter({ hasText: name })).toContainText('Deactivated')
})

test('an incomplete venue is refused and the fields are named (AC5)', async ({ page }) => {
  await signIn(page, 'venue-staff@example.com')

  // Submit the empty form: nothing typed, so every required field should come back named.
  await page.getByRole('button', { name: 'Add venue' }).click()

  await expect(page.getByText('Name is required')).toBeVisible()
  await expect(page.getByText('Location is required')).toBeVisible()
  await expect(page.getByText('Maximum capacity is required')).toBeVisible()
  await expect(page.getByText('Supported layouts is required')).toBeVisible()
  // Nothing was saved, so no confirmation appears.
  await expect(page.getByRole('status').filter({ hasText: 'added to the catalogue' })).toHaveCount(
    0,
  )
})

test('a coordinator sees the catalogue but cannot change it (AC2, AC4)', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  // AC2: the seeded active venues are readable...
  await expect(catalogue(page).filter({ hasText: 'Mochtar Riady Auditorium' })).toContainText(
    'up to 500 people',
  )
  // ...with no control that would create, edit or deactivate one.
  await expect(page.getByRole('button', { name: 'Deactivate' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add venue' })).toHaveCount(0)

  // AC3: the seeded deactivated venue is not in the selectable catalogue a coordinator sees.
  await expect(catalogue(page).filter({ hasText: 'Old Sports Hall' })).toHaveCount(0)
})

test('venue staff see deactivated venues that coordinators do not (AC3, AC4)', async ({ page }) => {
  await signIn(page, 'venue-staff@example.com')

  // AC4: the deactivated seed venue keeps its details and is still readable to staff.
  const retired = catalogue(page).filter({ hasText: 'Old Sports Hall' })
  await expect(retired).toContainText('Deactivated')
  await expect(retired).toContainText('up to 300 people')
  await expect(retired.getByRole('button', { name: 'Reactivate' })).toBeVisible()
})

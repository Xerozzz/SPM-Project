import { expect, type Page, test } from '@playwright/test'

// SCRUM-59: reading the catalogue and adding to it, in the browser.
//
// Relies on the dev seed (scripts/seed.py), which the api container runs on every start:
// three venues, one of them ("Old Sports Hall") deactivated, so AC3 is visible without
// this test having to change anything.
//
// The venue the add test creates is named with a timestamp so the file can be re-run
// against the same database: names are unique and nothing here deletes a venue.

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

function catalogue(page: Page) {
  return section(page).getByRole('listitem')
}

test('a coordinator reads the catalogue and cannot add to it (AC2)', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  await expect(catalogue(page).filter({ hasText: 'Mochtar Riady Auditorium' })).toContainText(
    'up to 500 people',
  )
  await expect(section(page).getByRole('button')).toHaveCount(0)
})

test('a deactivated venue is not offered for planning (AC3)', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  await expect(catalogue(page).filter({ hasText: 'Old Sports Hall' })).toHaveCount(0)
})

test('venue staff add a venue (AC1)', async ({ page }) => {
  const name = `E2E Hall ${Date.now()}`
  await signIn(page, 'venue-staff@example.com')

  await page.getByLabel(/^Name/).fill(name)
  await page.getByLabel(/^Location/).fill('Level 4, Campus Green')
  await page.getByLabel(/^Maximum capacity/).fill('120')
  await page.getByLabel('classroom').check()
  await page.getByLabel(/^Facilities/).fill('Projector, Hearing loop')
  await page.getByLabel(/^Accessibility features/).fill('Step-free access')
  await page.getByLabel(/^Opens at/).fill('09:00')
  await page.getByLabel(/^Closes at/).fill('18:00')
  await page.getByRole('button', { name: 'Add venue' }).click()

  // Home also has a role="status" line for API health, so pick ours by its text.
  await expect(page.getByRole('status').filter({ hasText: name })).toContainText(
    `“${name}” has been added to the catalogue.`,
  )
  const added = catalogue(page).filter({ hasText: name })
  await expect(added).toContainText('up to 120 people')
  await expect(added).toContainText('Facilities: Projector, Hearing loop')
  await expect(added).toContainText('Accessibility: Step-free access')
  await expect(added).toContainText('09:00 to 18:00')
})

test('an incomplete venue is refused and the fields are named (AC5)', async ({ page }) => {
  await signIn(page, 'venue-staff@example.com')

  // Submit the empty form: nothing typed, so every required field should come back named.
  await page.getByRole('button', { name: 'Add venue' }).click()

  await expect(page.getByText('Name is required')).toBeVisible()
  await expect(page.getByText('Location is required')).toBeVisible()
  await expect(page.getByText('Maximum capacity is required')).toBeVisible()
  await expect(page.getByText('Supported layouts is required')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'added to the catalogue' })).toHaveCount(
    0,
  )
})

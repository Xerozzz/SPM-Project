import { expect, type Page, test } from '@playwright/test'

// SCRUM-59: the venue catalogue through the browser.
//
// Relies on the dev seed (scripts/seed.py), which the api container runs on every start:
// three venues, one of them ("Old Sports Hall") deactivated, so AC3 is visible without this
// test having to deactivate anything first.
//
// The venue this test adds is named with a timestamp so the file can be re-run against the
// same database. Venue names are unique and deactivation is not a delete (ADR-0012), so a
// fixed name would collide with the row left by the previous run.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page
    .getByRole('button', {
      name: email.startsWith('venue-staff') ? 'Venue Catalogue' : 'Venue Planning',
      exact: true,
    })
    .click()
  await expect(
    page.getByRole('heading', {
      name: email.startsWith('venue-staff') ? 'Venue Catalogue' : 'Venue Planning',
      exact: true,
    }),
  ).toBeVisible()
}

function catalogue(page: Page) {
  return page.locator('main > section:not([hidden])').getByRole('listitem')
}

test('venue staff add, edit and deactivate a venue (AC1, AC3)', async ({ page }) => {
  const name = `E2E Hall ${Date.now()}`
  await signIn(page, 'venue-staff@example.com')

  await page.getByRole('button', { name: 'Add venue', exact: true }).click()
  await page.getByLabel(/^Name/).fill(name)
  await page.getByLabel(/^Setup time/).fill('0')
  await page.getByLabel(/^Turnaround time/).fill('0')
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

  // AC1's update half: reopen the venue, change it, and save.
  await added.getByRole('button', { name: `Edit ${name}` }).click()
  await expect(page.getByLabel(/^Name/)).toHaveValue(name)
  await page.getByLabel(/^Maximum capacity/).fill('150')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('status').filter({ hasText: name })).toContainText(
    `“${name}” has been updated.`,
  )
  await expect(catalogue(page).filter({ hasText: name })).toContainText('up to 150 people')

  // AC3: deactivating takes it out of the selectable catalogue, without deleting it.
  await catalogue(page)
    .filter({ hasText: name })
    .getByRole('button', { name: `Deactivate ${name}` })
    .click()
  await expect(page.getByRole('status').filter({ hasText: name })).toContainText(
    `“${name}” has been deactivated and can no longer be selected.`,
  )
  await expect(catalogue(page).filter({ hasText: name })).toHaveCount(0)
})

test('an incomplete venue is refused and the fields are named (AC5)', async ({ page }) => {
  await signIn(page, 'venue-staff@example.com')

  await page.getByRole('button', { name: 'Add venue', exact: true }).click()
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

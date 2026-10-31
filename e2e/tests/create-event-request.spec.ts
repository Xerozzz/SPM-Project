import { expect, type Page, test } from '@playwright/test'

// SCRUM-28: an organiser creates one complete event request through the UI.
//
// There is one form, with two ways out of it. "Create event request" is for a request the
// organiser is finished with: it goes straight for review. "Save draft" keeps an unfinished
// one without asking anyone to look at it. Both are covered here; what happens to a draft
// afterwards belongs to the submission story.

async function signInAsOrganiser(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('organiser@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: /Create event$/ }).click()
  await expect(page.getByRole('heading', { name: 'New event request' })).toBeVisible()
}

function row(page: Page, name: string) {
  return page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name, exact: true }) })
}

async function fillCompleteForm(page: Page, name: string) {
  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Hall A')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
}

test('an organiser creates a complete event request and it goes for review', async ({ page }) => {
  const name = `E2E orientation ${Date.now()}`
  await signInAsOrganiser(page)

  await fillCompleteForm(page, name)
  await page.getByRole('button', { name: 'Create event request' }).click()

  // Home also has a role="status" line for API health, so pick ours by its text.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  await expect(row(page, name)).toContainText('Submitted')
})

test('an organiser saves an event request as a draft without sending it', async ({ page }) => {
  const name = `E2E draft ${Date.now()}`
  await signInAsOrganiser(page)

  await fillCompleteForm(page, name)
  await page.getByRole('button', { name: 'Save draft' }).click()

  await expect(page.getByRole('status').filter({ hasText: 'saved as a draft' })).toContainText(
    `“${name}” has been saved as a draft.`,
  )
  await expect(row(page, name)).toContainText('Draft')
  await row(page, name)
    .getByRole('button', { name: `View details for ${name}` })
    .click()
  // Still the organiser's to finish: details offer the saved draft for editing.
  await expect(row(page, name).getByRole('button', { name: `Edit draft ${name}` })).toBeVisible()
})

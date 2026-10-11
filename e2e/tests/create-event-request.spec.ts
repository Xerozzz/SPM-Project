import { expect, type Page, test } from '@playwright/test'

// SCRUM-28/SCRUM-29: an organiser saves one complete event request as a draft through the
// unified event-request form.

async function signInAsOrganiser(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('organiser@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'New event request' })).toBeVisible()
}

function row(page: Page, name: string) {
  const ownRequests = page
    .getByRole('heading', { name: 'My event requests' })
    .locator('..')
    .getByRole('list')
  return ownRequests.getByRole('listitem').filter({
    has: page.getByText(name, { exact: true }),
  })
}

test('an organiser creates a complete event request as a draft', async ({ page }) => {
  const name = `E2E orientation ${Date.now()}`
  await signInAsOrganiser(page)

  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Auditorium-type venue')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector-type requirement')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
  await page.getByRole('button', { name: 'Save draft' }).click()

  await expect(page.getByRole('status').filter({ hasText: 'saved as a draft' })).toContainText(
    `“${name}” was saved as a draft.`,
  )
  await expect(row(page, name)).toContainText('Draft')
})

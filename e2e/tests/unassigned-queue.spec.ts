import { expect, type Page, test } from '@playwright/test'

// TC-101-08: an organiser submits a request, then a Lead signs in and sees it in the
// unassigned queue with every required field.
test.describe.configure({ retries: 0 })

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
}

function ownRow(page: Page, name: string) {
  const ownRequests = page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
  return ownRequests.getByRole('listitem').filter({ hasText: name })
}

test('an organiser submission appears in the Lead unassigned queue', async ({ page }) => {
  const name = `E2E unassigned ${Date.now()}`
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()

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
  await page.getByRole('button', { name: 'Create event request' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'has been created' }),
  ).toContainText(`“${name}” has been created.`)
  await ownRow(page, name).getByRole('button', { name: 'Submit for review' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'submitted for review' }),
  ).toContainText(`“${name}” has been submitted for review.`)
  await signOut(page)

  await signIn(page, 'coordinator-lead@example.com')
  const queue = page.getByLabel('Unassigned requests')
  await expect(queue).toBeVisible()
  const entry = queue.getByRole('listitem').filter({ hasText: name })
  await expect(entry).toContainText(name)
  await expect(entry).toContainText('Expected attendance')
  await expect(entry).toContainText('200')
  await expect(entry).toContainText('Submitted')
})

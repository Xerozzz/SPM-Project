import { expect, type Page, test } from '@playwright/test'

// SCRUM-46: an organiser submits an event request through the UI.
//
// The complete-submit case creates its own draft so it can be rerun without depending on
// mutable seed state. The incomplete case uses the seeded "Hackathon (draft)" row.
test.describe.configure({ retries: 0 })

async function signInAsOrganiser(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('organiser@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()
}

function row(page: Page, name: string) {
  const ownRequests = page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
  return ownRequests.getByRole('listitem').filter({ hasText: name })
}

async function createCompleteDraft(page: Page, name: string) {
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
  // Save draft, not Create: creating sends the request for review in the same press,
  // and this test needs a draft that nobody has looked at yet.
  await page.getByRole('button', { name: 'Save draft' }).click()

  await expect(page.getByRole('status').filter({ hasText: 'saved as a draft' })).toContainText(
    `“${name}” has been saved as a draft.`,
  )
}

test('a complete draft is submitted and confirmed (AC1), then locked (AC3)', async ({ page }) => {
  const name = `E2E submit ${Date.now()}`
  await signInAsOrganiser(page)
  await createCompleteDraft(page, name)

  await expect(row(page, name)).toContainText('Draft')
  await row(page, name).getByRole('button', { name: 'Submit for review' }).click()

  // Home also has a role="status" line for API health, so pick ours by its text.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review. Its status is now Submitted.`,
  )
  await expect(row(page, name)).toContainText('Submitted')
  await expect(row(page, name)).toContainText('Locked')
  await expect(
    row(page, name).getByRole('button', {
      name: 'Submit for review',
    }),
  ).toHaveCount(0)
})

test('an incomplete draft is refused and the fields are named (AC2)', async ({ page }) => {
  await signInAsOrganiser(page)

  await row(page, 'Hackathon (draft)').getByRole('button', { name: 'Submit for review' }).click()

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('“Hackathon (draft)” cannot be submitted yet')
  await expect(alert).toContainText('Description is required')
  await expect(alert).toContainText('End date and time is required')
  await expect(alert).toContainText('Expected attendance is required')
  await expect(row(page, 'Hackathon (draft)')).toContainText('Draft')
})

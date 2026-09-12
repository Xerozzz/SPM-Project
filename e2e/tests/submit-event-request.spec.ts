import { expect, type Page, test } from '@playwright/test'

// SCRUM-46: an organiser submits an event request through the UI.
//
// Relies on the dev seed (scripts/seed.py), which the api container runs on every start:
// organiser@example.com owns "Orientation Day" (complete) and "Hackathon (draft)"
// (incomplete), both recreated in Draft. The first test genuinely submits the request, so
// it can only pass once per seed: re-running locally needs `make seed` first, and retries
// are off for this file so a failure is reported as itself rather than as "already
// submitted". Once SCRUM-28 adds POST /api/event-requests, this should create its own
// draft instead of consuming shared seed data.
test.describe.configure({ retries: 0 })

async function signInAsOrganiser(page: Page) {
  await page.goto('/')
  await page.getByLabel('Email').fill('organiser@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()
}

function row(page: Page, name: string) {
  return page.getByRole('listitem').filter({ hasText: name })
}

test('a complete draft is submitted and confirmed (AC1), then locked (AC3)', async ({ page }) => {
  await signInAsOrganiser(page)

  await expect(row(page, 'Orientation Day')).toContainText('Draft')
  await row(page, 'Orientation Day').getByRole('button', { name: 'Submit for review' }).click()

  // Home also has a role="status" line for API health, so pick ours by its text.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    '“Orientation Day” has been submitted for review. Its status is now Submitted.',
  )
  await expect(row(page, 'Orientation Day')).toContainText('Submitted')
  await expect(row(page, 'Orientation Day')).toContainText('Locked')
  await expect(
    row(page, 'Orientation Day').getByRole('button', {
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

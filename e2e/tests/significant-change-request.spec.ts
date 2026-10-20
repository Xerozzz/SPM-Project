import { expect, type Page, test } from '@playwright/test'

// SCRUM-37: after submission the owning Organiser proposes a significant change instead of
// editing, and the assigned Coordinator sees the proposed value next to the current one.
// Uses the seeded Approved "Careers Fair" (attendance 180), owned by organiser@example.com
// and assigned to coordinator@example.com. Proposing changes nothing on the event.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

function ownRow(page: Page, name: string) {
  return page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
    .getByRole('listitem')
    .filter({ hasText: name })
}

const REASON = `E2E more sign-ups ${Date.now()}`

test('an organiser proposes a change and the coordinator can compare it', async ({ page }) => {
  await signIn(page, 'organiser@example.com')
  const row = ownRow(page, 'Careers Fair')
  await row.getByRole('button', { name: 'Propose a change to Careers Fair' }).click()
  const form = row.getByRole('form', { name: 'Propose a change' })

  // AC4: an invalid value is refused and nothing is recorded.
  await form.getByLabel('Attendance').fill('0')
  await form.getByLabel('Reason for the change').fill(REASON)
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('alert')).toContainText('must be a positive whole number')
  await expect(row.getByRole('article').filter({ hasText: REASON })).toHaveCount(0)

  // AC1, AC3: a valid proposal is recorded as pending, with the current value kept.
  await form.getByLabel('Attendance').fill('220')
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('status')).toContainText('Change request sent')
  const proposal = row.getByRole('article').filter({ hasText: REASON })
  await expect(proposal).toContainText('Pending review')
  await expect(proposal.getByRole('row').filter({ hasText: 'Attendance' })).toContainText('180')
  await expect(proposal.getByRole('row').filter({ hasText: 'Attendance' })).toContainText('220')
  await page.getByRole('button', { name: 'Sign out' }).click()

  // AC5, AC6: the coordinator sees the same pending request, and the event is unchanged.
  await signIn(page, 'coordinator@example.com')
  const card = page.getByRole('article').filter({ hasText: 'Careers Fair' }).first()
  await expect(card.getByText(REASON)).toBeVisible()
  await expect(card.getByText('Attendance:').locator('..')).toContainText('180')
})

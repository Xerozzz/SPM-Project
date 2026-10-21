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

// Every value this file proposes is unique to the run, and anything it leaves pending is
// rejected at the end, so a local re-run against the same database works like CI's fresh
// one: an approved change from an earlier run never makes this run's proposal a no-op.
const RUN = Date.now()
const REASON = `E2E more sign-ups ${RUN}`

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

  // AC1, AC3: a valid proposal is recorded as pending, with the current value kept. The
  // current attendance is read from the form rather than assumed from the seed.
  const current = await form.getByLabel('Attendance').inputValue()
  const proposed = String(Number(current) + 40)
  await form.getByLabel('Attendance').fill(proposed)
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('status')).toContainText('Change request sent')
  const proposal = row.getByRole('article').filter({ hasText: REASON })
  await expect(proposal).toContainText('Pending review')
  const attendanceRow = proposal.getByRole('row').filter({ hasText: 'Attendance' })
  await expect(attendanceRow).toContainText(current)
  await expect(attendanceRow).toContainText(proposed)
  await page.getByRole('button', { name: 'Sign out' }).click()

  // AC5, AC6: the coordinator sees the same pending request, and the event is unchanged.
  await signIn(page, 'coordinator@example.com')
  const card = page.getByRole('article').filter({ hasText: 'Careers Fair' }).first()
  const request = card.getByRole('article').filter({ hasText: REASON })
  await expect(request).toBeVisible()
  await expect(card.getByText('Attendance:').locator('..')).toContainText(current)

  // SCRUM-47 AC6: rejecting keeps the event as it was. This also leaves nothing pending
  // behind for the next run.
  await request.getByLabel('Decision note').fill('Hall cannot take more people')
  await request.getByRole('button', { name: 'Reject change' }).click()
  await expect(request).toContainText('Rejected')
  await expect(card.getByText('Attendance:').locator('..')).toContainText(current)
})

// SCRUM-47: the assigned Coordinator approves a pending change with a note, and the
// event's own value changes while the request shows what was applied.
const LAYOUT_REASON = `E2E new layout ${RUN}`
const LAYOUT = `Cabaret style ${RUN}`

test('the coordinator approves a change and it is applied', async ({ page }) => {
  await signIn(page, 'organiser@example.com')
  const row = ownRow(page, 'Careers Fair')
  await row.getByRole('button', { name: 'Propose a change to Careers Fair' }).click()
  const form = row.getByRole('form', { name: 'Propose a change' })
  await form.getByLabel('Layout').fill(LAYOUT)
  await form.getByLabel('Reason for the change').fill(LAYOUT_REASON)
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('status')).toContainText('Change request sent')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await signIn(page, 'coordinator@example.com')
  const card = page.getByRole('article').filter({ hasText: 'Careers Fair' }).first()
  const request = card.getByRole('article').filter({ hasText: LAYOUT_REASON })
  await request.getByLabel('Decision note').fill('Cabaret fits the hall')
  await request.getByRole('button', { name: 'Approve change' }).click()

  await expect(request).toContainText('Approved')
  await expect(request).toContainText('Cabaret fits the hall')
  await expect(request.getByRole('row').filter({ hasText: 'Layout' })).toContainText('Applied')
  await expect(card.getByText('Layout:').locator('..')).toContainText(LAYOUT)
})

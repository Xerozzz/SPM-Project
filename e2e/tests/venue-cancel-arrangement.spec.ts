import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { openEvent } from '../support/workspace'
import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-109, TC-109-01: the assigned Coordinator cancels one of two venue arrangements
// from the event page, with a reason; it shows as Cancelled and the other is unchanged.
//
// Self-contained and re-runnable: a fresh Approved event, its own venue and session
// labels stamped with the run, all on VENUE_SPEC_ACCOUNT, so it never uses coordinator@
// and has nothing to hand back.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function post(request: APIRequestContext, token: string, path: string, data: unknown) {
  const response = await request.post(`${API}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  })
  expect(response.ok(), `POST ${path} -> ${response.status()} ${await response.text()}`).toBe(true)
  return response.json() as Promise<{ id: string }>
}

/** An Approved event with two pending requests at a venue of its own. */
async function eventWithTwoArrangements(request: APIRequestContext) {
  const stamp = Date.now()
  const event = await createApprovedEvent(request, { name: `E2E cancel ${stamp}`, lane: 1 })
  const staff = await tokenFor(request, 'venue-staff@example.com')
  const venue = await post(request, staff, '/api/venues', {
    name: `E2E Cancel Hall ${stamp}`,
    location: 'E2E cancel spec',
    maximum_capacity: 200,
    facilities: ['Projector'],
    supported_layouts: ['theatre'],
    accessibility_features: ['Step-free access'],
    opens_at: '00:00:00',
    closes_at: '23:59:00',
    setup_minutes: 0,
    turnaround_minutes: 0,
  })
  const coordinator = await tokenFor(request, VENUE_SPEC_ACCOUNT)
  const middle = new Date((Date.parse(event.start_at) + Date.parse(event.end_at)) / 2)
  const sessions = { morning: `Morning ${stamp}`, afternoon: `Afternoon ${stamp}` }
  for (const [session_label, start_at, end_at] of [
    [sessions.morning, event.start_at, middle.toISOString()],
    [sessions.afternoon, middle.toISOString(), event.end_at],
  ]) {
    await post(request, coordinator, `/api/event-requests/${event.id}/venue-bookings`, {
      venue_id: venue.id,
      session_label,
      start_at,
      end_at,
    })
  }
  return { event, sessions }
}

test('TC-109-01: the assigned Coordinator cancels one arrangement and the other stays', async ({
  page,
}) => {
  const {
    event,
    sessions: { morning, afternoon },
  } = await eventWithTwoArrangements(page.request)
  const reason = `Moved online ${Date.now()}`

  await signIn(page, VENUE_SPEC_ACCOUNT)
  const card = await openEvent(page, event.name, 'Review Queue')
  // Rows are anchored on their stamped session labels: this account's board holds every
  // earlier run's events too.
  const morningRow = card.getByRole('listitem').filter({ hasText: morning })
  const afternoonRow = card.getByRole('listitem').filter({ hasText: afternoon })
  await page
    .getByRole('button', { name: `Cancel arrangement for ${morning}` })
    .click({ timeout: 15000 })

  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText(`Cancel ${morning} at E2E Cancel Hall`)
  const confirm = dialog.getByRole('button', { name: 'Confirm cancellation' })
  await expect(confirm).toBeDisabled()
  await dialog.getByLabel('Reason for cancelling').fill(reason)
  await confirm.click()

  await expect(dialog).toBeHidden()
  await expect(morningRow).toContainText('Status: cancelled')
  await expect(morningRow).toContainText('Cancelled by you:')
  await expect(morningRow).toContainText(`Reason: ${reason}`)
  await expect(page.getByRole('button', { name: `Cancel arrangement for ${morning}` })).toHaveCount(
    0,
  )

  await expect(afternoonRow).toContainText('Status: pending')
  await expect(afternoonRow).not.toContainText('Cancelled by')
  await expect(
    page.getByRole('button', { name: `Cancel arrangement for ${afternoon}` }),
  ).toBeVisible()
})

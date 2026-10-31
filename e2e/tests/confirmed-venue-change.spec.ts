import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { openEvent } from '../support/workspace'
import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-118: the assigned Coordinator cancels one arrangement of a Confirmed event. That
// is a venue change: the event goes back to planning, the arrangement is Cancelled, and
// the event's other arrangement is left as it was.
//
// Set up as confirm-event.spec.ts does, through the API, then driven on the real screen.
// It books a venue it creates for itself and stamps its session labels with the run, so
// it is re-runnable and never competes with the other venue specs for a slot.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function call(
  request: APIRequestContext,
  token: string,
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  data?: unknown,
) {
  const response = await request.fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  })
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBe(
    true,
  )
  return response.json() as Promise<Record<string, string>>
}

/** A Confirmed event with two committed sessions at a venue of its own. */
async function confirmedEventWithTwoArrangements(request: APIRequestContext) {
  const stamp = Date.now()
  const event = await createApprovedEvent(request, { name: `E2E venue change ${stamp}`, lane: 2 })
  const staff = await tokenFor(request, 'venue-staff@example.com')
  const venue = await call(request, staff, 'POST', '/api/venues', {
    name: `E2E Venue Change Hall ${stamp}`,
    location: 'E2E venue change spec',
    maximum_capacity: 200,
    facilities: ['Projector'],
    supported_layouts: ['theatre'],
    accessibility_features: ['Step-free access'],
    opens_at: '00:00:00',
    closes_at: '23:59:00',
    setup_minutes: 0,
    turnaround_minutes: 0,
  })

  // Two holds, one per session. SCRUM-83: a hold expires an hour before the event starts.
  const coordinator = await tokenFor(request, VENUE_SPEC_ACCOUNT)
  const middle = new Date((Date.parse(event.start_at) + Date.parse(event.end_at)) / 2)
  const sessions = { morning: `Morning ${stamp}`, afternoon: `Afternoon ${stamp}` }
  for (const [session_label, start_at, end_at] of [
    [sessions.morning, event.start_at, middle.toISOString()],
    [sessions.afternoon, middle.toISOString(), event.end_at],
  ]) {
    const booking = await call(
      request,
      coordinator,
      'POST',
      `/api/event-requests/${event.id}/venue-bookings`,
      { venue_id: venue.id, session_label, start_at, end_at },
    )
    await call(request, staff, 'POST', `/api/venue-bookings/${booking.id}/hold`, {
      expires_at: new Date(Date.parse(event.start_at) - 3_600_000).toISOString(),
    })
  }

  const requirements = (await call(
    request,
    coordinator,
    'GET',
    `/api/event-requests/${event.id}/equipment-requirements`,
  )) as unknown as { id: string }[]
  const tech = await tokenFor(request, 'tech-support@example.com')
  await call(request, tech, 'PATCH', `/api/equipment-requirements/${requirements[0].id}/review`, {
    review_status: 'available',
  })
  await call(
    request,
    tech,
    'POST',
    `/api/event-requests/${event.id}/equipment-requirements/${requirements[0].id}/reserve`,
    {},
  )

  // The Safety Officer approves the plan exactly as it stands (SCRUM-79, ADR-0048).
  const officer = await tokenFor(request, 'safety-officer@example.com')
  const plan = await call(request, officer, 'GET', `/api/safety-reviews/${event.id}`)
  await call(request, officer, 'POST', `/api/safety-reviews/${event.id}`, {
    decision: 'approve',
    comment: 'Egress and capacity check out.',
    plan_fingerprint: plan.plan_fingerprint,
  })

  await call(request, coordinator, 'POST', `/api/event-requests/${event.id}/confirm`)
  return { event, coordinator, sessions }
}

test('SCRUM-118: a venue change returns a Confirmed event to planning', async ({ page }) => {
  const { event, coordinator, sessions } = await confirmedEventWithTwoArrangements(page.request)
  const { morning, afternoon } = sessions
  const reason = `Hall flooded ${Date.now()}`

  await signIn(page, VENUE_SPEC_ACCOUNT)
  const card = await openEvent(page, event.name, 'Review Queue')
  await page
    .getByRole('button', { name: `Cancel arrangement for ${morning}` })
    .click({ timeout: 15000 })

  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('The event returns to planning')
  const start = dialog.getByRole('button', { name: 'Start venue change' })
  await dialog.getByLabel('Reason for cancelling').fill(reason)
  await expect(start).toBeDisabled()
  await dialog.getByLabel('I understand this returns the event to planning').check()
  await start.click()

  await expect(page.getByRole('status').filter({ hasText: event.name })).toContainText(
    'is back in planning',
  )
  // Back in planning, the card is the Approved one again and SCRUM-109's list shows the
  // cancelled arrangement with its reason. Rows are anchored on their stamped labels.
  await expect(page.getByRole('button', { name: `Confirm ${event.name}` })).toBeVisible()
  const morningRow = card.getByRole('listitem').filter({ hasText: morning })
  const afternoonRow = card.getByRole('listitem').filter({ hasText: afternoon })
  await expect(morningRow).toContainText('Status: cancelled')
  await expect(morningRow).toContainText(`Reason: ${reason}`)
  await expect(afternoonRow).toContainText('Status: confirmed')
  await expect(afternoonRow).not.toContainText('Cancelled by')

  // The same, as the API records it.
  const planned = await call(page.request, coordinator, 'GET', `/api/event-requests/${event.id}`)
  expect(planned.status).toBe('approved')
})

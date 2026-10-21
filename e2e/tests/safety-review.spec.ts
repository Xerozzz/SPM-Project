import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-79: a Safety Officer reviews an event's plan and records a decision.
//
// The plan is assembled from three roles' work, so the spec arranges one through the real
// API — the Coordinator requests a venue, Venue Staff hold it, Technical Support assess
// and reserve the equipment — and then drives the screen as the Officer. That is the only
// automated proof the screen and the API agree about what a plan is and when it may be
// judged.
//
// It books a venue it creates for itself rather than a seeded one, so it never competes
// with the venue specs for a slot whatever order they run in or how often they re-run.

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
  // The body, not just the code: a 422 here means a payload this spec got wrong, and
  // the reason is in the body.
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBe(
    true,
  )
  return response.json() as Promise<Record<string, string>>
}

/** A venue only this run uses, so no other spec's hold or closure can occupy it. */
async function ownVenue(request: APIRequestContext, name: string) {
  const staff = await tokenFor(request, 'venue-staff@example.com')
  return call(request, staff, 'POST', '/api/venues', {
    name,
    location: 'E2E safety spec',
    maximum_capacity: 200,
    facilities: ['Projector'],
    supported_layouts: ['theatre'],
    accessibility_features: ['Step-free access'],
    opens_at: '00:00:00',
    closes_at: '23:59:00',
    setup_minutes: 0,
    turnaround_minutes: 0,
  })
}

test('a Safety Officer reviews an arranged plan and records a decision', async ({ page }) => {
  const stamp = Date.now()
  const event = await createApprovedEvent(page.request, {
    name: `E2E safety review ${stamp}`,
    lane: 2,
  })
  const venue = await ownVenue(page.request, `E2E Safety Hall ${stamp}`)

  // The Coordinator asks for the venue, and Venue Staff hold it (SCRUM-110: approving a
  // request places a tentative hold, which is what AC2 counts as arranged).
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const booking = await call(
    page.request,
    coordinator,
    'POST',
    `/api/event-requests/${event.id}/venue-bookings`,
    {
      venue_id: venue.id,
      session_label: 'Main session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  )
  const staff = await tokenFor(page.request, 'venue-staff@example.com')
  // SCRUM-83: a hold may not outlast the event start, so it expires an hour before.
  const expiresAt = new Date(Date.parse(event.start_at) - 3_600_000).toISOString()
  await call(page.request, staff, 'POST', `/api/venue-bookings/${booking.id}/hold`, {
    expires_at: expiresAt,
  })

  // Technical Support assess the equipment and reserve it, the other half of AC2.
  // Approving the event already turned the Organiser's stated need into a requirement
  // record, so this reviews the one that is there rather than adding a second.
  const requirements = (await call(
    page.request,
    coordinator,
    'GET',
    `/api/event-requests/${event.id}/equipment-requirements`,
  )) as unknown as { id: string; equipment_type: string }[]
  const requirement = requirements[0]
  expect(requirement, 'the approved event has an equipment requirement').toBeDefined()
  const tech = await tokenFor(page.request, 'tech-support@example.com')
  await call(page.request, tech, 'PATCH', `/api/equipment-requirements/${requirement.id}/review`, {
    review_status: 'available',
  })
  await call(
    page.request,
    tech,
    'POST',
    `/api/event-requests/${event.id}/equipment-requirements/${requirement.id}/reserve`,
    {},
  )

  await signIn(page, 'safety-officer@example.com')

  // AC1 and AC3: the event is ready to review, with the plan a decision is about.
  const card = page.getByRole('article').filter({ hasText: event.name })
  await expect(card).toBeVisible({ timeout: 15000 })
  await expect(card.getByText('Main session')).toBeVisible()
  await expect(card.getByText('Tentative hold')).toBeVisible()
  await expect(card.getByText('Available')).toBeVisible()
  await expect(card.getByText('This plan cannot be reviewed yet.')).toBeHidden()

  // AC4: a decision needs a reason, and the reason is what the Coordinator reads.
  await expect(card.getByRole('button', { name: `Approve the plan for ${event.name}` })).toBeDisabled()
  await card.getByLabel('Reason for this decision').fill('Egress and capacity check out.')
  await card.getByRole('button', { name: `Approve the plan for ${event.name}` }).click()

  // AC8: the approval is recorded, and it does not confirm the event.
  await expect(card.getByRole('status')).toContainText('This does not confirm the event.')

  // AC9: the decision is in the event's history, with the reason it was given for.
  await card.getByRole('button', { name: 'Past decisions' }).click()
  await expect(card.getByText('Egress and capacity check out.').first()).toBeVisible()
})

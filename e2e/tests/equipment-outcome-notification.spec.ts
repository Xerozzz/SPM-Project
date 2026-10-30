import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-125: when Technical Support reviews or reserves equipment, the assigned
// Coordinator is told in their inbox, with a link to the authorised coordinator view.
// Anyone else's inbox stays quiet.
//
// The event is Approved (not Confirmed) so its equipment can still be reviewed and
// reserved, and the requirement is the seeded Projector line the approval carries
// across — no catalogue lookup needed.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
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

function outcomeEntries(page: Page, eventId: string) {
  return page
    .getByLabel('Notifications', { exact: true })
    .getByRole('listitem')
    .filter({ hasText: /equipment_review_available|equipment_reserved_full/ })
    .filter({ hasText: eventId })
}

test('a review and a reservation each tell the Coordinator, with a link to their events', async ({
  page,
}) => {
  const approved = await createApprovedEvent(page.request, {
    name: `E2E equipment outcome ${Date.now()}`,
    lane: 2,
  })

  // Technical Support reviews the seeded Projector line, then reserves it in full.
  const tech = await tokenFor(page.request, 'tech-support@example.com')
  const requirements = (await call(
    page.request,
    tech,
    'GET',
    '/api/equipment-requirements/review',
  )) as unknown as { id: string; event_request_id: string }[]
  const row = requirements.find((entry) => entry.event_request_id === approved.id)
  expect(row, 'the seeded Projector requirement for this event').toBeDefined()
  await call(page.request, tech, 'PATCH', `/api/equipment-requirements/${row!.id}/review`, {
    review_status: 'available',
  })
  await call(
    page.request,
    tech,
    'POST',
    `/api/event-requests/${approved.id}/equipment-requirements/${row!.id}/reserve`,
  )

  // The assigned Coordinator sees both outcomes in their inbox, with the view link.
  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: /^Notifications/ }).click()
  const entries = outcomeEntries(page, approved.id)
  await expect(entries).toHaveCount(2)
  await expect(
    entries.first().getByRole('link', { name: 'View equipment outcome' }),
  ).toHaveAttribute('href', '#coordinator-events')
  await signOut(page)

  // An unrelated user is told nothing.
  await signIn(page, 'attendee@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(outcomeEntries(page, approved.id)).toHaveCount(0)
})

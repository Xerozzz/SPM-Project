import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-124: when the Coordinator adds or changes an equipment requirement, Technical
// Support Staff are told in their inbox, with a link to the authorised review queue.
// Anyone else's inbox stays quiet.
//
// The event is Approved (not Confirmed) so the Coordinator can still maintain its
// equipment, and the requirement is added through the real API the way the product
// does it.

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

function reviewEntries(page: Page, eventId: string) {
  return page
    .getByLabel('Notifications')
    .getByRole('listitem')
    .filter({ hasText: 'equipment_review_needed' })
    .filter({ hasText: eventId })
}

test('a new equipment requirement tells Technical Support, with a link to the review queue', async ({
  page,
}) => {
  const approved = await createApprovedEvent(page.request, {
    name: `E2E equipment review ${Date.now()}`,
    lane: 1,
  })

  // The Coordinator adds a requirement through the real endpoint. The event already
  // carries the seeded Projector line, so pick any other active catalogue type —
  // hardcoding one breaks whenever the seed or catalogue state changes.
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const catalogue = (await call(
    page.request,
    coordinator,
    'GET',
    `/api/event-requests/${approved.id}/equipment-requirements/catalogue-types`,
  )) as unknown as string[]
  const freshType = catalogue.find((type) => type !== 'Projector')
  expect(freshType, 'an active catalogue type besides Projector').toBeDefined()
  await call(
    page.request,
    coordinator,
    'POST',
    `/api/event-requests/${approved.id}/equipment-requirements`,
    { equipment_type: freshType, quantity: 2 },
  )

  // Technical Support Staff see it in their inbox, with the review link.
  await signIn(page, 'tech-support@example.com')
  const entry = reviewEntries(page, approved.id)
  await expect(entry).toHaveCount(1)
  await expect(entry.getByRole('link', { name: 'Review equipment requirements' })).toHaveAttribute(
    'href',
    '#equipment-review-queue',
  )
  await signOut(page)

  // An unrelated user is told nothing.
  await signIn(page, 'attendee@example.com')
  await expect(reviewEntries(page, approved.id)).toHaveCount(0)
})

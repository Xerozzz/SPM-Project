import { expect, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// TC-110-07: Venue Staff approval of a Pending venue booking creates a time-limited
// tentative hold — not a confirmation — and the hold survives a reload.
//
// The Pending booking is set up through the real booking API as the coordinator
// assigned to an Approved event this spec creates for itself; the approval itself goes
// through the Venue Staff UI with a hold expiry, which is what this story changed.

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

// One seeded active venue is enough. The event is the spec's own, on a day no other
// run or spec uses (support/approved-event.ts), so the new request is conflict-free on
// a reseeded database and on a local one that keeps earlier runs' holds alike. A
// conflict here still means the product code regressed, not the data.
const VENUE_NAME = 'Hall A'

function singaporeDisplay(value: string) {
  return new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
}

/** The Singapore wall clock `days` before an instant, as the hold inputs take it. */
function singaporeInputBefore(iso: string, days: number) {
  const at = new Date(iso).getTime() - days * 24 * 3_600_000
  return new Date(at + 8 * 3_600_000).toISOString().slice(0, 16)
}

test('SCRUM-110 and SCRUM-121: approval and an expiry update survive reload', async ({ page }) => {
  // An Approved event of the spec's own, then a Pending request for Hall A for its
  // whole period, made as its assigned coordinator through the booking API.
  const event = await createApprovedEvent(page.request, {
    name: `E2E approval hold ${Date.now()}`,
    lane: 0,
  })
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${coordinator}` }
  const venues = (await (await page.request.get(`${API}/api/venues`, { headers })).json()) as {
    id: string
    name: string
  }[]
  const venue = venues.find((row) => row.name === VENUE_NAME)
  if (!venue) throw new Error(`Seeded venue ${VENUE_NAME} missing`)
  const created = await page.request.post(`${API}/api/event-requests/${event.id}/venue-bookings`, {
    headers,
    data: {
      venue_id: venue.id,
      session_label: 'Approval hold session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  })
  expect(created.ok(), `booking request -> ${created.status()}`).toBe(true)

  // Venue Staff approve the Pending request with a hold expiry.
  await signIn(page, 'venue-staff@example.com')
  const section = page.locator('main section', {
    has: page.getByRole('heading', { name: 'Venue booking requests' }),
  })
  const card = section
    .getByRole('article')
    .filter({ hasText: event.name })
    .filter({ hasText: VENUE_NAME })
    .first()
  await expect(card).toBeVisible()
  // Both expiries sit before the event starts, as the API requires, wherever its day is.
  await card.getByLabel('Hold until (Singapore time)').fill(singaporeInputBefore(event.start_at, 2))
  await card.getByRole('button', { name: 'Approve' }).click()
  // The request left Pending for the Tentative holds section — it was never confirmed,
  // so its card offers no approval control anymore. The hold text itself is the proof
  // the approval committed (the outcome line renders alongside it).
  const heldCard = section
    .getByRole('article')
    .filter({ hasText: event.name })
    .filter({ hasText: VENUE_NAME })
    .first()
  await expect(heldCard).toContainText(/Tentative hold until/)
  await expect(heldCard.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await expect(section.getByRole('status')).toContainText('is on a tentative hold')

  // Venue Staff revise the active hold through SCRUM-121's control. The new current
  // expiry is visible immediately and remains the only expiry after reload.
  const revisedInput = singaporeInputBefore(event.start_at, 1)
  const revisedInstant = new Date(`${revisedInput}:00+08:00`).toISOString()
  await heldCard.getByLabel('New expiry (Singapore time)').fill(revisedInput)
  await heldCard.getByRole('button', { name: 'Update expiry' }).click()
  await expect(section.getByRole('status')).toContainText('hold expiry')
  await expect(heldCard).toContainText(`Tentative hold until ${singaporeDisplay(revisedInstant)}`)

  // A reload keeps both the Tentative status and the revised current expiry.
  await page.reload()
  const reloaded = page.locator('main section', {
    has: page.getByRole('heading', { name: 'Venue booking requests' }),
  })
  const reloadedHold = reloaded
    .getByRole('article')
    .filter({ hasText: event.name })
    .filter({ hasText: VENUE_NAME })
    .first()
  await expect(reloadedHold).toContainText(
    `Tentative hold until ${singaporeDisplay(revisedInstant)}`,
  )
  await signOut(page)
})

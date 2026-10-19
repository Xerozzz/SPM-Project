import { expect, type Page, test } from '@playwright/test'

// TC-110-07: Venue Staff approval of a Pending venue booking creates a time-limited
// tentative hold — not a confirmation — and the hold survives a reload.
//
// The Pending booking is set up through the real booking API as the coordinator
// assigned to the seeded Approved "Careers Fair" event; the approval itself goes
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

// One seeded active venue is enough: CI reseeds before every run, so the database
// starts with no holds and the new request is conflict-free. (A previous version of
// this spec tried each venue in turn to survive local re-runs against a dirty DB,
// but with only three venues and one bookable event that fallback just hid real
// failures — a conflict here means the product code regressed, not the seed.)
const VENUE_NAME = 'Hall A'

test('approving a pending venue booking creates a tentative hold that survives reload', async ({
  page,
}) => {
  await signIn(page, 'coordinator@example.com')

  // Find the seeded Approved event and request Hall A for it through the same
  // reads the UI uses.
  const setup = await page.evaluate(async (venueName: string) => {
    const raw = localStorage.getItem('connectsphere.token')
    const token = raw ? (JSON.parse(raw) as { token: string }).token : ''
    const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    // Relative /api paths would hit the web dev server, so resolve them against the API.
    const api = `${window.location.protocol}//${window.location.hostname}:8000`
    const bookable = (await (
      await fetch(`${api}/api/event-requests/bookable`, { headers })
    ).json()) as { id: string; name: string }[]
    const event = bookable.find((row) => row.name === 'Careers Fair')
    const venues = (await (await fetch(`${api}/api/venues`, { headers })).json()) as {
      id: string
      name: string
    }[]
    if (!event) return null
    const venue = venues.find((row) => row.name === venueName)
    if (!venue) return null
    const created = await fetch(`${api}/api/event-requests/${event.id}/venue-bookings`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ venue_id: venue.id }),
    })
    if (!created.ok) return null
    return { venueName }
  }, VENUE_NAME)
  if (!setup) throw new Error('Could not create a Careers Fair booking at Hall A')
  await signOut(page)

  // Venue Staff approve the Pending request with a hold expiry.
  await signIn(page, 'venue-staff@example.com')
  const section = page.locator('main section', { has: page.getByRole('heading', { name: 'Venue booking requests' }) })
  const card = section
    .getByRole('article')
    .filter({ hasText: 'Careers Fair' })
    .filter({ hasText: setup.venueName })
    .first()
  await expect(card).toBeVisible()
  await card.getByLabel('Hold until (Singapore time)').fill('2026-12-01T10:00')
  await card.getByRole('button', { name: 'Approve' }).click()
  // The request left Pending for the Tentative holds section — it was never confirmed,
  // so its card offers no approval control anymore. The hold text itself is the proof
  // the approval committed (the outcome line renders alongside it).
  const heldCard = section
    .getByRole('article')
    .filter({ hasText: 'Careers Fair' })
    .filter({ hasText: setup.venueName })
    .first()
  await expect(heldCard).toContainText(/Tentative hold until/)
  await expect(heldCard.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await expect(section.getByRole('status')).toContainText('is on a tentative hold')

  // A reload keeps the hold: approval persisted a Tentative booking, not a transient state.
  await page.reload()
  const reloaded = page.locator('main section', { has: page.getByRole('heading', { name: 'Venue booking requests' }) })
  await expect(
    reloaded
      .getByRole('article')
      .filter({ hasText: 'Careers Fair' })
      .filter({ hasText: setup.venueName })
      .first(),
  ).toContainText(/Tentative hold until/)
  await signOut(page)
})

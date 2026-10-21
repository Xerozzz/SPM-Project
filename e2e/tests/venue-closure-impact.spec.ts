import { expect, type Page, test } from '@playwright/test'

import { createApprovedEvent, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-81 and SCRUM-116: Venue Staff record a closure over a live venue hold. The closure is saved,
// the affected arrangement is listed, nothing is cancelled, and the assigned
// Coordinator gets a closure-impact notification.
//
// The hold is set up through the real API at the auditorium, on an Approved event this
// spec creates for itself on a day no other run or spec uses (support/approved-event.ts).
// The closure therefore touches only this spec's event, even while other venue specs
// run in parallel, and earlier runs' holds and notifications cannot be mistaken for it.

const VENUE_NAME = 'Mochtar Riady Auditorium'

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function api<T>(page: Page, path: string, method = 'GET', body?: unknown): Promise<T> {
  return page.evaluate(
    async ({ path, method, body }) => {
      const raw = localStorage.getItem('connectsphere.token')
      const token = raw ? (JSON.parse(raw) as { token: string }).token : ''
      const base = `${window.location.protocol}//${window.location.hostname}:8000`
      const response = await fetch(`${base}${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      if (!response.ok) throw new Error(`${method} ${path} -> ${response.status}`)
      return (await response.json()) as T
    },
    { path, method, body },
  )
}

/** The instant as a datetime-local input in the browser's own timezone wants it. */
async function localInput(page: Page, value: string): Promise<string> {
  return page.evaluate((iso) => {
    const at = new Date(iso)
    return new Date(at.getTime() - at.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  }, value)
}

test('a closure over a live hold is saved, listed and notified', async ({ page }) => {
  const event = await createApprovedEvent(page.request, {
    name: `E2E closure impact ${Date.now()}`,
    lane: 2,
  })
  await signIn(page, VENUE_SPEC_ACCOUNT)
  const venue = (await api<{ id: string; name: string }[]>(page, '/api/venues')).find(
    (row) => row.name === VENUE_NAME,
  )
  if (!venue) throw new Error('Seeded auditorium missing')
  const booking = await api<{ id: string }>(
    page,
    `/api/event-requests/${event.id}/venue-bookings`,
    'POST',
    {
      venue_id: venue.id,
      session_label: 'Closure impact session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  )
  await page.getByRole('button', { name: 'Sign out' }).click()

  await signIn(page, 'venue-staff@example.com')
  const expires = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
  await api(page, `/api/venue-bookings/${booking.id}/approve`, 'POST', { expires_at: expires })

  // The closure manager's own section, not the catalogue section around it.
  const section = page.locator('section:has(> h2:text-is("Venue unavailability"))')
  await section.locator('select').first().selectOption({ label: VENUE_NAME })
  const start = new Date(event.start_at)
  await section.getByLabel('Start date and time').fill(await localInput(page, start.toISOString()))
  await section
    .getByLabel('End date and time')
    .fill(await localInput(page, new Date(start.getTime() + 3600_000).toISOString()))
  await section.getByLabel('Reason').fill('Burst pipe')
  await section.getByRole('button', { name: 'Record unavailability' }).click()

  const status = section.getByRole('status')
  await expect(status).toContainText('It affects 1 live arrangement')
  await expect(status).toContainText(`${event.name}, Closure impact session (tentative)`)
  await expect(status).toContainText('Nothing was cancelled')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await signIn(page, VENUE_SPEC_ACCOUNT)
  // This event's own closure-impact notification: earlier runs left others in the inbox,
  // and this event also has an assignment notification.
  await expect(
    page
      .getByRole('region', { name: 'Notifications' })
      .getByRole('listitem', { name: new RegExp(`notification for event ${event.id}$`) })
      .filter({ hasText: 'venue_closure_impact' }),
  ).toBeVisible()
  // AC2, AC3: the existing booking list shows the arrangement needs action.
  const card = page.getByRole('article').filter({ hasText: event.name })
  await expect(card.getByText(/Needs attention\. The venue is closed/)).toBeVisible()

  // SCRUM-116 AC1 to AC3: start a linked replacement at another venue from the affected
  // arrangement. The session and its times are carried over.
  await card.getByRole('button', { name: 'Find a replacement for Closure impact session' }).click()
  await expect(card.getByRole('note')).toContainText('Requesting a replacement')
  await card.getByLabel('Active venue').selectOption({ label: 'SCIS Seminar Room 2-1' })
  await card.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(
    card.getByText(`Replacement for Closure impact session at ${VENUE_NAME}.`),
  ).toBeVisible()
  await expect(
    card.getByText('Replacement requested at SCIS Seminar Room 2-1 (pending).'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()

  // Clean up so no closure is left on the auditorium for later runs or specs. Removing
  // it clears the derived marker with nothing else to undo (AC6).
  await signIn(page, 'venue-staff@example.com')
  const closures = await api<{ id: string }[]>(page, `/api/venues/${venue.id}/unavailabilities`)
  for (const closure of closures) {
    await page.evaluate(
      async ({ venueId, id }) => {
        const raw = localStorage.getItem('connectsphere.token')
        const token = raw ? (JSON.parse(raw) as { token: string }).token : ''
        const base = `${window.location.protocol}//${window.location.hostname}:8000`
        await fetch(`${base}/api/venues/${venueId}/unavailabilities/${id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
      },
      { venueId: venue.id, id: closure.id },
    )
  }
})

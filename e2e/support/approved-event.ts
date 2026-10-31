import { expect, type APIRequestContext } from '@playwright/test'

/**
 * A fresh Approved event, made through the real API the way the product makes one: the
 * Organiser creates and submits it, the Lead assigns it, the assigned Coordinator
 * approves it. `VENUE_SPEC_ACCOUNT` is both that Organiser and that Coordinator.
 *
 * The venue specs used to share the seeded "Careers Fair". That only worked on a freshly
 * seeded database with one spec at a time: locally the database keeps earlier runs' holds
 * and closures, and Playwright runs spec files in parallel, so the specs collided on the
 * same venue slot. Each spec now books its own event, on its own day, under its own name.
 */

/**
 * The seeded account that owns and coordinates every event made here. It is both an
 * Organiser and a Coordinator, and no other spec signs in as it, so these events never
 * land in the lists other specs read: coordinator@'s review page and organiser@'s
 * requests stay as they were. Approved events cannot be cancelled through the API, so
 * keeping them out of shared accounts is the only clean-up a test can do.
 */
export const VENUE_SPEC_ACCOUNT = 'multi-role@example.com'

export interface ApprovedEvent {
  id: string
  name: string
  start_at: string
  end_at: string
}

// Use the same Vite API proxy as the browser, so isolated stacks can use another port.
const WEB = new URL(process.env.E2E_BASE_URL ?? 'http://localhost:5173')
export const API = WEB.origin

/** A bearer token for a seeded account, straight from the login endpoint. */
export async function tokenFor(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/api/auth/login`, {
    data: { email, password: 'password123' },
  })
  expect(response.ok(), `sign-in as ${email}`).toBe(true)
  return ((await response.json()) as { access_token: string }).access_token
}

/**
 * 10:00 to 12:00 Singapore time on a day no earlier run or other spec uses.
 *
 * The day comes from the second the spec starts (so even a re-run straight after the
 * last one moves on) plus the spec's `lane` (so specs started in the same second differ),
 * roughly 1 to 25 years ahead. Two runs only share a day if they start a whole multiple
 * of 3,000 seconds (50 minutes) apart to the second, and even then `freeWindow` below
 * moves past a day that an earlier run's hold or closure still occupies.
 */
export function uniqueWindow(lane: 0 | 1 | 2, skip = 0): { start_at: string; end_at: string } {
  const slot = Math.floor(Date.now() / 1_000) % 3_000
  // `skip` moves on in steps of three days, so a spec stays in its own lane.
  const days = 400 + (slot + skip) * 3 + lane
  const today = new Date()
  const day = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + days)
  // 02:00 UTC is 10:00 in Singapore (UTC+8, no daylight saving): inside venue hours.
  const start = new Date(day + 2 * 3_600_000)
  const end = new Date(day + 4 * 3_600_000)
  return { start_at: start.toISOString(), end_at: end.toISOString() }
}

// Every seeded venue the venue specs book, hold or close.
const SPEC_VENUES = ['Hall A', 'Mochtar Riady Auditorium', 'SCIS Seminar Room 2-1']

/**
 * The first window, from `uniqueWindow`, in which nothing holds any of the spec venues:
 * no confirmed booking, tentative hold or closure, buffers included. That is the product's
 * own availability rule, so a leftover from an earlier run can never block this run.
 * Pending requests do not block, and they sit on other runs' events, not this one.
 */
async function freeWindow(request: APIRequestContext, lane: 0 | 1 | 2) {
  const token = await tokenFor(request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${token}` }
  const venues = (await (await request.get(`${API}/api/venues`, { headers })).json()) as {
    id: string
    name: string
  }[]
  const ids = SPEC_VENUES.map((name) => {
    const venue = venues.find((row) => row.name === name)
    expect(venue, `seeded venue ${name}`).toBeDefined()
    return venue!.id
  })
  for (let skip = 0; skip < 20; skip += 1) {
    const window = uniqueWindow(lane, skip)
    const verdicts = await Promise.all(
      ids.map(async (venueId) => {
        const response = await request.get(`${API}/api/venue-calendar/availability`, {
          headers,
          params: { venue_id: venueId, ...window },
        })
        expect(response.ok(), `availability -> ${response.status()}`).toBe(true)
        return ((await response.json()) as { available: boolean }).available
      }),
    )
    if (verdicts.every(Boolean)) return window
  }
  throw new Error('No free window for the venue specs in 20 tries')
}

/** One API call that must succeed, as the given account's token. */
async function call(
  request: APIRequestContext,
  token: string,
  method: 'GET' | 'POST',
  path: string,
  data?: unknown,
) {
  const response = await request.fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  })
  expect(response.ok(), `${method} ${path} -> ${response.status()}`).toBe(true)
  return response.json()
}

type EventOptions = { name: string; lane: 0 | 1 | 2; coordinator?: string }

/**
 * SCRUM-88: a fresh Submitted event the Lead has assigned, not yet approved, for a spec
 * that needs the Submitted stage (internal notes can only be recorded then). The same
 * steps `createApprovedEvent` starts with, and the same hand-back rule for `coordinator`.
 */
export async function createAssignedEvent(
  request: APIRequestContext,
  { name, lane, coordinator: assignee = VENUE_SPEC_ACCOUNT }: EventOptions,
): Promise<ApprovedEvent> {
  const window = await freeWindow(request, lane)
  const organiser = await tokenFor(request, VENUE_SPEC_ACCOUNT)
  const created = (await call(request, organiser, 'POST', '/api/event-requests', {
    name,
    purpose: 'E2E venue booking',
    description: 'Created by a venue spec so it owns its own venue slot.',
    ...window,
    expected_attendance: 30,
    venue_requirement: 'Hall A',
    accessibility_requirement: 'Step-free access',
    equipment_requirement: 'Projector',
    layout_requirement: 'Theatre style',
    registration_requirement: 'Open registration',
  })) as ApprovedEvent
  await call(request, organiser, 'POST', `/api/event-requests/${created.id}/submit`)

  const lead = await tokenFor(request, 'coordinator-lead@example.com')
  const coordinators = (await call(
    request,
    lead,
    'GET',
    '/api/event-requests/assignable-coordinators',
  )) as { id: string; email: string }[]
  const coordinator = coordinators.find((row) => row.email === assignee)
  expect(coordinator, `${assignee} is assignable`).toBeDefined()
  await call(request, lead, 'POST', `/api/event-requests/${created.id}/assign`, {
    coordinator_id: coordinator!.id,
  })
  return { id: created.id, name: created.name, start_at: created.start_at, end_at: created.end_at }
}

/**
 * `coordinator` is who the Lead assigns and who approves; it defaults to
 * `VENUE_SPEC_ACCOUNT`. A spec that needs the owner and the assignee to be different
 * people passes another account, and must hand the event back afterwards so it does
 * not stay on that account's review page (see significant-change-request.spec.ts).
 */
export async function createApprovedEvent(
  request: APIRequestContext,
  options: EventOptions,
): Promise<ApprovedEvent> {
  const assigned = await createAssignedEvent(request, options)
  const assignee = await tokenFor(request, options.coordinator ?? VENUE_SPEC_ACCOUNT)
  const approved = (await call(
    request,
    assignee,
    'POST',
    `/api/event-requests/${assigned.id}/approve`,
  )) as ApprovedEvent & { status: string }
  expect(approved.status).toBe('approved')
  return {
    id: approved.id,
    name: approved.name,
    start_at: approved.start_at,
    end_at: approved.end_at,
  }
}

import type { BookingConflict } from './venueBookingDecisions'

/**
 * Venue catalogue API calls (SCRUM-59). Mirrors api/schemas/venues.py.
 */

/** The closed layout vocabulary from domain/venue.py. */
export const ROOM_LAYOUTS = [
  'theatre',
  'classroom',
  'banquet',
  'boardroom',
  'u_shape',
  'standing',
] as const

export type RoomLayout = (typeof ROOM_LAYOUTS)[number]

export interface Venue {
  id: string
  name: string
  location: string
  maximum_capacity: number
  facilities: string[]
  supported_layouts: RoomLayout[]
  accessibility_features: string[]
  /** Wall-clock opening hours as "HH:MM:SS"; see domain/venue.py for why they are not UTC. */
  opens_at: string
  closes_at: string
  /**
   * SCRUM-82: minutes the venue needs to prepare before a booking and to reset after it.
   * A booking occupies the venue from its start minus setup to its end plus turnaround,
   * which is what availability and conflict detection compare (AC3, AC4).
   */
  setup_minutes: number
  turnaround_minutes: number
  /** A deactivated venue stays readable but cannot be chosen for new work (ADR-0012). */
  is_active: boolean
}

/** Everything Venue Staff supply when adding or changing a venue. */
export interface VenueInput {
  name: string
  location: string
  maximum_capacity: number | null
  facilities: string[]
  supported_layouts: string[]
  accessibility_features: string[]
  /** null when Venue Staff have not entered a time yet; the API names it as required. */
  opens_at: string | null
  closes_at: string | null
  /** SCRUM-82 AC1: whole minutes, zero or more. Null means no buffer. */
  setup_minutes: number | null
  turnaround_minutes: number | null
}

/** One field Venue Staff must fix before the record can be saved (AC5). */
export interface VenueProblem {
  field: string
  reason: string
}

export interface VenueUnavailability {
  id: string
  venue_id: string
  starts_at: string
  ends_at: string
  reason: string
}

export interface VenueUnavailabilityInput {
  starts_at: string | null
  ends_at: string | null
  reason: string
}

/** Thrown when the API refuses a save and names the fields to correct. */
export class VenueRejectedError extends Error {
  readonly problems: VenueProblem[]

  constructor(problems: VenueProblem[]) {
    super('The venue could not be saved')
    this.name = 'VenueRejectedError'
    this.problems = problems
  }
}

/** A validation refusal for one or more unavailability fields (SCRUM-62). */
export class VenueUnavailabilityRejectedError extends Error {
  readonly problems: VenueProblem[]

  constructor(problems: VenueProblem[]) {
    super('The unavailability period could not be saved')
    this.name = 'VenueUnavailabilityRejectedError'
    this.problems = problems
  }
}

function asVenueProblems(detail: unknown): VenueProblem[] | null {
  if (!Array.isArray(detail)) return null
  const problems = detail.filter(
    (item): item is VenueProblem =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as VenueProblem).field === 'string' &&
      typeof (item as VenueProblem).reason === 'string',
  )
  return problems.length === detail.length ? problems : null
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function jsonHeaders(token: string): HeadersInit {
  return { ...authHeaders(token), 'Content-Type': 'application/json' }
}

async function readVenue<T extends Venue = Venue>(response: Response): Promise<T> {
  if (response.status === 422) {
    const body = (await response.json()) as { detail: unknown }
    const problems = asVenueProblems(body.detail)
    // A 422 the API did not build from domain/venue.py (a malformed payload, say) has a
    // different shape. Reporting it as a plain error beats rendering an empty field list
    // that leaves the user staring at a form with no explanation.
    if (problems === null) throw new Error('The venue could not be saved (422)')
    throw new VenueRejectedError(problems)
  }
  if (response.status === 409) {
    throw new VenueRejectedError([{ field: 'name', reason: 'is already used by another venue' }])
  }
  if (!response.ok) throw new Error(`The venue could not be saved (${response.status})`)
  return (await response.json()) as T
}

/** The venues that may be chosen for new work. */
export async function listVenues(token: string): Promise<Venue[]> {
  const response = await fetch('/api/venues', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load the venue catalogue (${response.status})`)
  return (await response.json()) as Venue[]
}

export async function createVenue(token: string, venue: VenueInput): Promise<Venue> {
  return readVenue(
    await fetch('/api/venues', {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify(venue),
    }),
  )
}

/**
 * SCRUM-89 AC6: a saved venue, and what the save did to its bookings.
 *
 * A superset of `Venue`, so anything that only wanted the venue still gets one.
 */
export interface UpdatedVenue extends Venue {
  buffer_change: {
    changed: boolean
    problems: ProblemBooking[]
  }
}

export async function updateVenue(
  token: string,
  id: string,
  changes: Partial<VenueInput>,
): Promise<UpdatedVenue> {
  return readVenue<UpdatedVenue>(
    await fetch(`/api/venues/${id}`, {
      method: 'PATCH',
      headers: jsonHeaders(token),
      body: JSON.stringify(changes),
    }),
  )
}

export async function deactivateVenue(token: string, id: string): Promise<Venue> {
  return readVenue(
    await fetch(`/api/venues/${id}/deactivate`, { method: 'POST', headers: authHeaders(token) }),
  )
}

/** The server's own explanation, when it sent one as a plain sentence. */
async function reasonFrom(response: Response): Promise<string | null> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown }
    return typeof body.detail === 'string' && body.detail.trim() !== '' ? body.detail : null
  } catch {
    return null
  }
}

async function readUnavailability(response: Response): Promise<VenueUnavailability> {
  if (response.status === 422) {
    const body = (await response.json()) as { detail: unknown }
    const problems = asVenueProblems(body.detail)
    if (problems !== null) throw new VenueUnavailabilityRejectedError(problems)
  }
  if (!response.ok) {
    // A 409 carries the reason as a sentence: the venue is inactive, or a confirmed
    // booking is in the way. Falling through to the status code alone threw away the
    // only part the person reading the screen can act on.
    const reason = await reasonFrom(response)
    throw new Error(reason ?? `The unavailability period could not be saved (${response.status})`)
  }
  return (await response.json()) as VenueUnavailability
}

export async function listVenueUnavailabilities(
  token: string,
  venueId: string,
): Promise<VenueUnavailability[]> {
  const response = await fetch(`/api/venues/${venueId}/unavailabilities`, {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load venue unavailability (${response.status})`)
  return (await response.json()) as VenueUnavailability[]
}

export async function createVenueUnavailability(
  token: string,
  venueId: string,
  input: VenueUnavailabilityInput,
): Promise<VenueUnavailability> {
  return readUnavailability(
    await fetch(`/api/venues/${venueId}/unavailabilities`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify(input),
    }),
  )
}

export async function updateVenueUnavailability(
  token: string,
  venueId: string,
  id: string,
  input: VenueUnavailabilityInput,
): Promise<VenueUnavailability> {
  return readUnavailability(
    await fetch(`/api/venues/${venueId}/unavailabilities/${id}`, {
      method: 'PUT',
      headers: jsonHeaders(token),
      body: JSON.stringify(input),
    }),
  )
}

export async function deleteVenueUnavailability(
  token: string,
  venueId: string,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/venues/${venueId}/unavailabilities/${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  if (!response.ok)
    throw new Error(`The unavailability period could not be deleted (${response.status})`)
}

/** SCRUM-55: coordinator venue search. Mirrors GET /api/venues/search. */
export interface VenueSearchInput {
  startDate: string
  startTime: string
  endDate: string
  endTime: string
  minimumCapacity?: number
  location?: string
  accessibility?: string
  facility?: string
  layout?: string
}

/**
 * Search fields are Singapore wall-clock values. Make that conversion explicit
 * rather than relying on the browser machine's timezone before sending UTC
 * instants to the API for overlap checks.
 */
function singaporeWallClockToUtc(date: string, time: string): string {
  return new Date(`${date}T${time}:00+08:00`).toISOString()
}

export async function searchVenues(token: string, input: VenueSearchInput): Promise<Venue[]> {
  const params = new URLSearchParams({
    start_at: singaporeWallClockToUtc(input.startDate, input.startTime),
    end_at: singaporeWallClockToUtc(input.endDate, input.endTime),
  })
  if (input.minimumCapacity !== undefined)
    params.set('minimum_capacity', String(input.minimumCapacity))
  if (input.location !== undefined) params.set('location', input.location)
  if (input.accessibility !== undefined) params.set('accessibility', input.accessibility)
  if (input.facility !== undefined) params.set('facility', input.facility)
  if (input.layout !== undefined) params.set('layout', input.layout)
  const response = await fetch(`/api/venues/search?${params}`, { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not search venues (${response.status})`)
  return (await response.json()) as Venue[]
}


/** SCRUM-89 AC4: one booking that cannot stand under its venue's current buffers. */
export interface ProblemBooking {
  booking_id: string
  /** Whose booking it is. The panel defers to the Coordinator, so it has to name them. */
  event_request_id: string
  event_name: string | null
  start_at: string
  end_at: string
  conflict: BookingConflict
}

/** SCRUM-89 AC4: a venue and everything at it that needs attention. */
export interface VenueProblems {
  venue_id: string
  venue_name: string
  venue_location: string
  setup_minutes: number
  turnaround_minutes: number
  is_active: boolean
  problems: ProblemBooking[]
}

/**
 * SCRUM-89 AC4: every booking anywhere needing attention, venues with none left out.
 *
 * Worked out by the API on each request rather than read from a stored flag, so an empty
 * list means nothing needs attention right now, not that nothing was ever flagged.
 */
export async function listBookingProblems(token: string): Promise<VenueProblems[]> {
  const response = await fetch('/api/venues/booking-problems', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Could not load booking problems (status ${response.status})`)
  return (await response.json()) as VenueProblems[]
}

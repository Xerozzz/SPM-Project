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
  opens_at: string
  closes_at: string
}

/** One field Venue Staff must fix before the record can be saved (AC5). */
export interface VenueProblem {
  field: string
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

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function jsonHeaders(token: string): HeadersInit {
  return { ...authHeaders(token), 'Content-Type': 'application/json' }
}

async function readVenue(response: Response): Promise<Venue> {
  if (response.status === 422) {
    const body = (await response.json()) as { detail: VenueProblem[] }
    throw new VenueRejectedError(body.detail)
  }
  if (response.status === 409) {
    throw new VenueRejectedError([{ field: 'name', reason: 'is already used by another venue' }])
  }
  if (!response.ok) throw new Error(`The venue could not be saved (${response.status})`)
  return (await response.json()) as Venue
}

/** The venues that may be chosen for new work. */
export async function listVenues(token: string): Promise<Venue[]> {
  const response = await fetch('/api/venues', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load the venue catalogue (${response.status})`)
  return (await response.json()) as Venue[]
}

/** Every venue including deactivated ones. Venue Staff only. */
export async function listAllVenues(token: string): Promise<Venue[]> {
  const response = await fetch('/api/venues/all', { headers: authHeaders(token) })
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

export async function updateVenue(
  token: string,
  id: string,
  changes: Partial<VenueInput>,
): Promise<Venue> {
  return readVenue(
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

export async function reactivateVenue(token: string, id: string): Promise<Venue> {
  return readVenue(
    await fetch(`/api/venues/${id}/reactivate`, { method: 'POST', headers: authHeaders(token) }),
  )
}

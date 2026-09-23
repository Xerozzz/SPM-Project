/**
 * Venue catalogue API calls (SCRUM-59). Mirrors api/schemas/venues.py.
 */

/** The closed layout vocabulary the catalogue stores. */
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
  /** Wall-clock opening hours as "HH:MM:SS"; see api/models/venue.py for why not UTC. */
  opens_at: string
  closes_at: string
  /** A deactivated venue stays readable but cannot be chosen for new work (ADR-0012). */
  is_active: boolean
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/** The venues that may be chosen for new work. */
export async function listVenues(token: string): Promise<Venue[]> {
  const response = await fetch('/api/venues', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load the venue catalogue (${response.status})`)
  return (await response.json()) as Venue[]
}

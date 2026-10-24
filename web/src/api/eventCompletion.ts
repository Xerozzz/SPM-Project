/**
 * SCRUM-86: the assigned Coordinator completes an event and keeps its closure record.
 *
 * Mirrors `/event-requests/{id}/complete`, `/closure-notes`, `/closure` and
 * `/assigned-completed`. No rules live here. Whether the event may be completed, and
 * who may read the record, are the API's answers.
 */
import type { EventRequest } from './eventRequests'

export interface ClosureNote {
  version: number
  /** Null when nobody recorded a count, which is not the same as zero. */
  actual_attendance: number | null
  notes: string | null
  recorded_by_id: string
  recorded_at: string
}

export interface Closure {
  event_request_id: string
  status: string
  completed_by_id: string | null
  completed_at: string | null
  current: ClosureNote | null
  /** Every version, oldest first. */
  history: ClosureNote[]
}

export interface ClosureInput {
  actual_attendance: number | null
  notes: string | null
}

function headers(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

async function read<T>(response: Response, fallback: string): Promise<T> {
  const body = (await response.json().catch(() => null)) as unknown
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body ? (body.detail as unknown) : null
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) {
      const reasons = detail
        .map((row: { field?: unknown; reason?: unknown }) =>
          typeof row.reason === 'string' ? `${String(row.field)} ${row.reason}` : null,
        )
        .filter((text): text is string => text !== null)
      if (reasons.length > 0) throw new Error(reasons.join('. '))
    }
    throw new Error(`${fallback} (${response.status})`)
  }
  return body as T
}

export async function completeEvent(
  token: string,
  eventId: string,
  input: ClosureInput,
): Promise<Closure> {
  const response = await fetch(`/api/event-requests/${eventId}/complete`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify(input),
  })
  return read<Closure>(response, 'The event could not be completed')
}

export async function correctClosure(
  token: string,
  eventId: string,
  input: ClosureInput,
): Promise<ClosureNote> {
  const response = await fetch(`/api/event-requests/${eventId}/closure-notes`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify(input),
  })
  return read<ClosureNote>(response, 'The correction could not be saved')
}

export async function readClosure(token: string, eventId: string): Promise<Closure> {
  const response = await fetch(`/api/event-requests/${eventId}/closure`, {
    headers: headers(token),
  })
  return read<Closure>(response, 'Could not load the closure record')
}

export async function listCompletedEvents(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/assigned-completed', {
    headers: headers(token),
  })
  return read<EventRequest[]>(response, 'Could not load completed events')
}

/** "120" is 120, "" is no count. Anything else is left for the API to refuse. */
export function attendanceOf(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

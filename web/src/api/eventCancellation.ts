/**
 * SCRUM-115: cancel a whole event, and the Organiser's requests to do so.
 *
 * Mirrors `/event-requests/{id}/cancellation-requests`, `/cancel`, `.../decline` and
 * `/cancellation`, and SCRUM-88's `/assigned-cancelled` and `/cancelled` lists. No rules
 * live here. Who may act, which events can be cancelled and which cancelled events each
 * viewer sees are the API's answers.
 */

export interface CancellationRequest {
  id: string
  status: 'pending' | 'applied' | 'declined'
  reason: string
  requested_by_id: string
  requested_at: string
  decided_by_id: string | null
  decided_at: string | null
  decision_note: string | null
}

export interface Cancellation {
  event_request_id: string
  status: string
  cancelled_by_id: string | null
  cancelled_at: string | null
  cancellation_reason: string | null
  /** Every request, oldest first. */
  requests: CancellationRequest[]
}

/** SCRUM-88 AC6: one cancelled event a Coordinator or Lead may open the history of. */
export interface CancelledEvent {
  id: string
  name: string | null
  start_at: string | null
  cancelled_at: string | null
  cancellation_reason: string | null
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

export async function requestCancellation(
  token: string,
  eventId: string,
  reason: string,
): Promise<CancellationRequest> {
  const response = await fetch(`/api/event-requests/${eventId}/cancellation-requests`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify({ reason }),
  })
  return read<CancellationRequest>(response, 'The request could not be sent')
}

export async function cancelEvent(
  token: string,
  eventId: string,
  input: { reason: string | null; request_id: string | null },
): Promise<Cancellation> {
  const response = await fetch(`/api/event-requests/${eventId}/cancel`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify(input),
  })
  return read<Cancellation>(response, 'The event could not be cancelled')
}

export async function declineCancellation(
  token: string,
  eventId: string,
  requestId: string,
  note: string,
): Promise<CancellationRequest> {
  const response = await fetch(
    `/api/event-requests/${eventId}/cancellation-requests/${requestId}/decline`,
    { method: 'POST', headers: headers(token), body: JSON.stringify({ note }) },
  )
  return read<CancellationRequest>(response, 'The request could not be declined')
}

export async function readCancellation(token: string, eventId: string): Promise<Cancellation> {
  const response = await fetch(`/api/event-requests/${eventId}/cancellation`, {
    headers: headers(token),
  })
  return read<Cancellation>(response, 'Could not load the cancellation')
}

/** SCRUM-88 AC6: the Coordinator's own cancelled events, or every one for a Lead. */
export async function listCancelledEvents(
  token: string,
  scope: 'assigned' | 'all',
): Promise<CancelledEvent[]> {
  const path = scope === 'assigned' ? 'assigned-cancelled' : 'cancelled'
  const response = await fetch(`/api/event-requests/${path}`, { headers: headers(token) })
  return read<CancelledEvent[]>(response, 'Could not load cancelled events')
}

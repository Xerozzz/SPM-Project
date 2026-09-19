export type ClarificationKind = 'request' | 'response'

export interface EventClarification {
  id: string
  event_request_id: string
  author_id: string
  /** Which side wrote it. Set by the API from the endpoint used, never inferred. */
  kind: ClarificationKind
  message: string
  created_at: string
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

async function readClarification(response: Response): Promise<EventClarification> {
  if (!response.ok) throw new Error(`Clarification request failed (${response.status})`)
  return (await response.json()) as EventClarification
}

export async function listClarifications(
  token: string,
  eventRequestId: string,
): Promise<EventClarification[]> {
  const response = await fetch(`/api/event-requests/${eventRequestId}/clarifications`, {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load clarifications (${response.status})`)
  return (await response.json()) as EventClarification[]
}

export async function requestClarification(
  token: string,
  eventRequestId: string,
  message: string,
): Promise<EventClarification> {
  const response = await fetch(`/api/event-requests/${eventRequestId}/clarifications`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  return readClarification(response)
}

export async function respondToClarification(
  token: string,
  eventRequestId: string,
  message: string,
): Promise<EventClarification> {
  const response = await fetch(`/api/event-requests/${eventRequestId}/clarifications/responses`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  return readClarification(response)
}

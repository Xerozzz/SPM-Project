/**
 * Notification inbox API calls (SCRUM-99). Mirrors api/schemas/notifications.py.
 */

export interface Notification {
  id: string
  event_request_id: string
  event_name?: string | null
  type: string
  source_type: string
  source_id: string
  occurred_at: string
  created_at: string
  viewed_at: string | null
  is_unread: boolean
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

export async function listNotifications(token: string): Promise<Notification[]> {
  const response = await fetch('/api/notifications', { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`/api/notifications responded ${response.status}`)
  }
  const body: unknown = await response.json()
  if (!Array.isArray(body)) throw new Error('Could not read the notification inbox')
  return body as Notification[]
}

export async function markNotificationViewed(token: string, id: string): Promise<Notification> {
  const response = await fetch(`/api/notifications/${id}/viewed`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not mark notification viewed (${response.status})`)
  }
  return (await response.json()) as Notification
}

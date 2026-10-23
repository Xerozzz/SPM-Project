/** SCRUM-113 operational registration intake controls. */

export interface RegistrationSettings {
  event_request_id: string
  registration_enabled: boolean
  opened_at: string | null
  closes_at: string | null
  suspended_at: string | null
  closed_at: string | null
  intake_open: boolean
}

function headers(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

async function result(response: Response): Promise<RegistrationSettings> {
  if (response.ok) return (await response.json()) as RegistrationSettings
  const detail = await response
    .json()
    .then((body: { detail?: unknown }) => String(body.detail ?? 'Registration update failed'))
    .catch(() => `Registration update failed (${response.status})`)
  throw new Error(detail)
}

export async function readRegistrationSettings(token: string, eventId: string) {
  return result(
    await fetch(`/api/event-requests/${eventId}/registration`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  )
}

export async function openRegistration(token: string, eventId: string, closesAt: string | null) {
  return result(
    await fetch(`/api/event-requests/${eventId}/registration/open`, {
      method: 'POST',
      headers: headers(token),
      body: JSON.stringify(closesAt ? { closes_at: new Date(closesAt).toISOString() } : {}),
    }),
  )
}

export async function extendRegistration(token: string, eventId: string, closesAt: string) {
  return result(
    await fetch(`/api/event-requests/${eventId}/registration/extend`, {
      method: 'POST',
      headers: headers(token),
      body: JSON.stringify({ closes_at: new Date(closesAt).toISOString() }),
    }),
  )
}

export async function closeRegistration(token: string, eventId: string) {
  return result(
    await fetch(`/api/event-requests/${eventId}/registration/close`, {
      method: 'POST',
      headers: headers(token),
    }),
  )
}

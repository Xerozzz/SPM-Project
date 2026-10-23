/** Attendee registration endpoints (SCRUM-42). */

export type RegistrationStatus = 'pending' | 'waitlisted' | 'accepted' | 'withdrawn' | 'cancelled'

export interface AttendeeEvent {
  id: string
  name: string | null
  description: string | null
  start_at: string | null
  end_at: string | null
}

export interface EventRegistration {
  id: string
  event_request_id: string
  status: RegistrationStatus
  submitted_at: string
  submission_order: number
}

export interface RegistrationSubmission {
  full_name: string
  age: number
  phone_number: string
  dietary_accessibility_notes: string | null
}

export class RegistrationValidationError extends Error {
  constructor(readonly fields: Partial<Record<keyof RegistrationSubmission, string>>) {
    super('Please correct the highlighted registration information.')
    this.name = 'RegistrationValidationError'
  }
}

function headers(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

export async function listOpenEvents(token: string): Promise<AttendeeEvent[]> {
  const response = await fetch('/api/attendee/events', { headers: headers(token) })
  if (!response.ok) throw new Error(`Could not load events (${response.status})`)
  return (await response.json()) as AttendeeEvent[]
}

export async function submitRegistration(
  token: string,
  eventId: string,
  submission: RegistrationSubmission,
): Promise<EventRegistration> {
  const response = await fetch(`/api/attendee/events/${eventId}/registrations`, {
    method: 'POST',
    headers: { ...headers(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  })
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: Array<{ loc?: unknown[]; msg?: string }> }
    const fields = Object.fromEntries(
      (body.detail ?? []).flatMap((problem) => {
        const field = problem.loc?.at(-1)
        return typeof field === 'string' ? [[field, problem.msg ?? 'is not valid']] : []
      }),
    ) as Partial<Record<keyof RegistrationSubmission, string>>
    throw new RegistrationValidationError(fields)
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) =>
        typeof body.detail === 'string'
          ? body.detail
          : 'You are already registered for this event.',
      )
      .catch(() => `Registration failed (${response.status})`)
    throw new Error(detail)
  }
  return (await response.json()) as EventRegistration
}

export async function readMyRegistration(
  token: string,
  eventId: string,
): Promise<EventRegistration | null> {
  const response = await fetch(`/api/attendee/events/${eventId}/registration`, {
    headers: headers(token),
  })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`Could not load registration (${response.status})`)
  return (await response.json()) as EventRegistration
}

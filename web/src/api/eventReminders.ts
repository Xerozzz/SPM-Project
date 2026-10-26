/**
 * SCRUM-85: reminders the Coordinator asks for before their event.
 *
 * Mirrors `/event-requests/{id}/reminders`. No rules live here: what counts as a valid
 * lead time is the API's answer, and this module carries the refusal back field by field
 * so the Coordinator sees which entry was wrong rather than "something was".
 */

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/** AC2: one configured lead time, and whether its occurrence has happened yet. */
export interface Reminder {
  id: string
  event_request_id: string
  lead_minutes: number
  /** AC6 and AC8: processed occurrences are history, not something waiting to fire. */
  processed_at: string | null
}

/** One reason a schedule was refused, as the API names it. */
export interface ReminderProblem {
  field: string
  reason: string
}

/** AC1: the schedule was refused whole, with every reason. */
export class InvalidScheduleError extends Error {
  readonly problems: ReminderProblem[]

  constructor(problems: ReminderProblem[]) {
    super('That reminder schedule was not saved.')
    this.name = 'InvalidScheduleError'
    this.problems = problems
  }
}

/**
 * Lead times the Coordinator is likely to want, so the common case is one click.
 *
 * Offered rather than imposed: the API takes any positive whole number of minutes, and
 * these are only the ones worth a button.
 */
export const COMMON_LEAD_TIMES: { minutes: number; label: string }[] = [
  { minutes: 60, label: '1 hour before' },
  { minutes: 1440, label: '1 day before' },
  { minutes: 10080, label: '1 week before' },
]

/** Minutes as something a person reads, rather than a number they have to divide. */
export function describeLeadTime(minutes: number): string {
  if (minutes % 10080 === 0) {
    const weeks = minutes / 10080
    return weeks === 1 ? '1 week before' : `${weeks} weeks before`
  }
  if (minutes % 1440 === 0) {
    const days = minutes / 1440
    return days === 1 ? '1 day before' : `${days} days before`
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60
    return hours === 1 ? '1 hour before' : `${hours} hours before`
  }
  return minutes === 1 ? '1 minute before' : `${minutes} minutes before`
}

async function problemsOf(response: Response): Promise<ReminderProblem[]> {
  const detail = await response
    .clone()
    .json()
    .then((body: { detail?: unknown }) => body.detail)
    .catch(() => null)
  if (!Array.isArray(detail)) return []
  return detail
    .filter((row): row is ReminderProblem => typeof row === 'object' && row !== null)
    .map((row) => ({ field: String(row.field), reason: String(row.reason) }))
}

export async function readReminders(token: string, eventId: string): Promise<Reminder[]> {
  const response = await fetch(`/api/event-requests/${eventId}/reminders`, {
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not load the reminder schedule (${response.status})`)
  }
  return (await response.json()) as Reminder[]
}

/** AC1: replace the whole schedule. A refusal leaves the stored one untouched. */
export async function writeReminders(
  token: string,
  eventId: string,
  leadMinutes: number[],
): Promise<Reminder[]> {
  const response = await fetch(`/api/event-requests/${eventId}/reminders`, {
    method: 'PUT',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_minutes: leadMinutes }),
  })
  if (response.status === 422) throw new InvalidScheduleError(await problemsOf(response))
  if (!response.ok) {
    throw new Error(`The reminder schedule could not be saved (${response.status})`)
  }
  return (await response.json()) as Reminder[]
}

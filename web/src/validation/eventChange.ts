import type {
  ChangePlan,
  ChangeRequestInput,
  EquipmentChange,
  SessionChange,
} from '../api/eventChangeRequests'
import type { EventStatus } from '../api/eventRequests'

/**
 * SCRUM-37: turns the Organiser's edited form into a change request that holds only what
 * changed. The API checks every value (AC4), so nothing here decides validity.
 */

/** Mirrors PROPOSABLE_STATUSES in api/domain/event_change.py (AC1, AC7). */
export function acceptsChangeRequest(status: EventStatus): boolean {
  return status === 'submitted' || status === 'approved' || status === 'confirmed'
}

/** The event fields a significant change may touch (AC2), with their labels. */
export const CHANGE_FIELDS = [
  ['start_at', 'Start'],
  ['end_at', 'End'],
  ['expected_attendance', 'Attendance'],
  ['venue_requirement', 'Venue'],
  ['accessibility_requirement', 'Accessibility'],
  ['layout_requirement', 'Layout'],
] as const

export type ChangeField = (typeof CHANGE_FIELDS)[number][0]

export interface SessionDraft {
  id: string
  label: string
  start: string
  end: string
}

export interface EquipmentDraft {
  id: string
  quantity: string
  technical: string
  remove: boolean
}

export interface NewEquipmentDraft {
  type: string
  quantity: string
}

export interface ChangeDraft {
  reason: string
  event: Record<ChangeField, string>
  sessions: SessionDraft[]
  equipment: EquipmentDraft[]
  added: NewEquipmentDraft[]
}

/** The stored UTC instant as a `datetime-local` input wants it: local time, no offset. */
export function toLocalInput(value: string | null | undefined): string {
  if (!value) return ''
  const at = new Date(value)
  const local = new Date(at.getTime() - at.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

/** A `datetime-local` value back to a UTC instant, so the API gets a timezone-aware value. */
function toUtc(value: string): string | undefined {
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? undefined : at.toISOString()
}

function text(value: unknown): string {
  return value === null || value === undefined ? '' : String(value)
}

/** The form starts from today's values. */
export function draftOf(plan: ChangePlan): ChangeDraft {
  const event = Object.fromEntries(
    CHANGE_FIELDS.map(([field]) => {
      const value = plan.event[field]
      return [field, field.endsWith('_at') ? toLocalInput(text(value)) : text(value)]
    }),
  ) as Record<ChangeField, string>
  return {
    reason: '',
    event,
    sessions: plan.sessions.map((s) => ({
      id: s.id,
      label: s.session_label,
      start: toLocalInput(s.start_at),
      end: toLocalInput(s.end_at),
    })),
    equipment: plan.equipment.map((e) => ({
      id: e.id,
      quantity: String(e.quantity),
      technical: e.technical_requirements ?? '',
      remove: false,
    })),
    added: [],
  }
}

/** Only the values that differ from the plan, so the request lists real changes (AC3). */
export function changeRequestOf(
  plan: ChangePlan,
  draft: ChangeDraft,
  submissionKey: string,
): ChangeRequestInput {
  const before = draftOf(plan)
  const event: Record<string, string | number | null> = {}
  for (const [field] of CHANGE_FIELDS) {
    const value = draft.event[field]
    if (value === before.event[field]) continue
    // A cleared date is sent as null, so the API names it as required.
    if (field.endsWith('_at')) event[field] = toUtc(value) ?? null
    else if (field === 'expected_attendance') event[field] = Number(value)
    else event[field] = value
  }

  const sessions: SessionChange[] = []
  for (const session of draft.sessions) {
    const old = before.sessions.find((s) => s.id === session.id)
    if (!old) continue
    const change: SessionChange = { booking_id: session.id }
    if (session.label !== old.label) change.session_label = session.label
    if (session.start !== old.start) change.start_at = toUtc(session.start)
    if (session.end !== old.end) change.end_at = toUtc(session.end)
    if (Object.keys(change).length > 1) sessions.push(change)
  }

  const equipment: EquipmentChange[] = []
  for (const line of draft.equipment) {
    const old = before.equipment.find((e) => e.id === line.id)
    if (!old) continue
    if (line.remove) {
      equipment.push({ requirement_id: line.id, remove: true })
      continue
    }
    const change: EquipmentChange = { requirement_id: line.id }
    if (line.quantity !== old.quantity) change.quantity = Number(line.quantity)
    if (line.technical !== old.technical) change.technical_requirements = line.technical
    if (Object.keys(change).length > 1) equipment.push(change)
  }
  for (const line of draft.added) {
    equipment.push({ equipment_type: line.type, quantity: Number(line.quantity) })
  }

  return { submission_key: submissionKey, reason: draft.reason, event, sessions, equipment }
}

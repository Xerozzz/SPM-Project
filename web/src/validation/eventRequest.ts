import type { EventRequest, EventRequestCreate, EventRequestDraftInput } from '../api/eventRequests'

export type EventRequestFormValues = Omit<
  EventRequestCreate,
  'expected_attendance' | 'start_at' | 'end_at'
> & {
  expected_attendance: string
  start_at: string
  end_at: string
}

export type EventRequestFieldName = keyof EventRequestFormValues
export type EventRequestFieldErrors = Partial<Record<EventRequestFieldName, string>>

export function emptyEventRequestForm(): EventRequestFormValues {
  return {
    name: '',
    purpose: '',
    description: '',
    start_at: '',
    end_at: '',
    expected_attendance: '',
    venue_requirement: '',
    accessibility_requirement: '',
    equipment_requirement: '',
    layout_requirement: '',
    registration_requirement: '',
  }
}

export function eventRequestToFormValues(request: EventRequest): EventRequestFormValues {
  return {
    name: request.name ?? '',
    purpose: request.purpose ?? '',
    description: request.description ?? '',
    start_at: toLocalDateTime(request.start_at),
    end_at: toLocalDateTime(request.end_at),
    expected_attendance: request.expected_attendance?.toString() ?? '',
    venue_requirement: request.venue_requirement ?? '',
    accessibility_requirement: request.accessibility_requirement ?? '',
    equipment_requirement: request.equipment_requirement ?? '',
    layout_requirement: request.layout_requirement ?? '',
    registration_requirement: request.registration_requirement ?? '',
  }
}

export function eventRequestToDraftInput(values: EventRequestFormValues): EventRequestDraftInput {
  return {
    name: nullableText(values.name),
    purpose: nullableText(values.purpose),
    description: nullableText(values.description),
    start_at: toUtc(values.start_at),
    end_at: toUtc(values.end_at),
    expected_attendance:
      values.expected_attendance.trim() === '' ? null : Number(values.expected_attendance),
    venue_requirement: nullableText(values.venue_requirement),
    accessibility_requirement: nullableText(values.accessibility_requirement),
    equipment_requirement: nullableText(values.equipment_requirement),
    layout_requirement: nullableText(values.layout_requirement),
    registration_requirement: nullableText(values.registration_requirement),
  }
}

export function validateEventRequest(values: EventRequestFormValues): EventRequestFieldErrors {
  const errors: EventRequestFieldErrors = {}

  for (const [name, value] of Object.entries(values)) {
    if (!value.trim()) errors[name as EventRequestFieldName] = 'This field is required.'
  }

  const attendance = Number(values.expected_attendance)
  if (values.expected_attendance && (!Number.isInteger(attendance) || attendance <= 0)) {
    errors.expected_attendance = 'Enter a positive whole number.'
  }

  if (values.start_at && values.end_at && new Date(values.end_at) <= new Date(values.start_at)) {
    errors.end_at = 'End date and time must be after the start date and time.'
  }

  if (values.start_at && new Date(values.start_at) <= new Date()) {
    errors.start_at = 'Start date and time must be in the future.'
  }

  return errors
}

function nullableText(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function toUtc(value: string): string | null {
  if (value.trim() === '') return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function toLocalDateTime(value: string | null): string {
  if (value === null) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 19)
}

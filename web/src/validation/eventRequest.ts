import type { EventRequestCreate } from '../api/eventRequests'

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

export function validateEventRequest(
  values: EventRequestFormValues,
): EventRequestFieldErrors {
  const errors: EventRequestFieldErrors = {}

  for (const [name, value] of Object.entries(values)) {
    if (!value.trim()) errors[name as EventRequestFieldName] = 'This field is required.'
  }

  const attendance = Number(values.expected_attendance)
  if (
    values.expected_attendance &&
    (!Number.isInteger(attendance) || attendance <= 0)
  ) {
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

/**
 * SCRUM-88: an event's history, read from the records each story already keeps (ADR-0062).
 *
 * `EventHistoryEntry` mirrors the API's `EventHistoryEntryRead` field for field, so the UI
 * has exactly the permitted fields (AC9): no more, because the API sends no more, and no
 * fewer, because the component shows each one.
 */

export type HistoryAction =
  | 'draft_created'
  | 'submitted'
  | 'review_decided'
  | 'coordinator_assigned'
  | 'coordinator_reassigned'
  | 'clarification_requested'
  | 'clarification_responded'
  | 'venue_requested'
  | 'venue_decided'
  | 'hold_created'
  | 'hold_confirmed'
  | 'hold_expired'
  | 'replacement_adopted'
  | 'arrangement_cancelled'
  | 'buffer_changed'
  | 'requirement_added'
  | 'requirement_updated'
  | 'requirement_removed'
  | 'equipment_reserved'
  | 'reservation_flagged'
  | 'reservation_released'
  | 'event_confirmed'
  | 'returned_to_planning'
  | 'event_cancelled'

export type HistorySource =
  | 'event_request'
  | 'coordinator_assignment'
  | 'clarification'
  | 'venue_booking'
  | 'venue_buffer_change'
  | 'equipment_requirement_change'
  | 'equipment_reservation'
  | 'safety_review'

/** SCRUM-120: why an event went back to planning. */
export type ReplanCause = 'change_request' | 'venue_closure' | 'venue_cancellation'

/** SCRUM-119: one value before and after, with its label. Only fields a reader names. */
export interface FieldChange {
  field: string
  label: string
  /** Null is "no value". */
  old: string | null
  new: string | null
}

export interface EventHistoryEntry {
  /** `action:source_id`, unique within one history. */
  id: string
  action: HistoryAction
  /** UTC; shown in Singapore time. */
  occurred_at: string
  /** Both null for the system (a hold's expiry); only the email null for a missing user. */
  actor_id: string | null
  actor_email: string | null
  source_type: HistorySource
  source_id: string
  outcome: 'approved' | 'rejected' | null
  reason: string | null
  previous_coordinator_email: string | null
  new_coordinator_email: string | null
  venue_name: string | null
  session_label: string | null
  hold_expires_at: string | null
  /** An internal note's text. The API sends note entries only to the current assignee. */
  note: string | null
  /** SCRUM-119: the venue session's period (UTC). */
  session_start_at: string | null
  session_end_at: string | null
  /** The other arrangement of a replacement: the one replaced, or the one replacing it. */
  related_booking_id: string | null
  /** The event's bookings a buffer change caught out. */
  affected_booking_ids: string[]
  changes: FieldChange[]
  /** SCRUM-119 AC6: the equipment type, and a reservation's quantity. */
  equipment_type: string | null
  quantity: number | null
  /** SCRUM-120: false when a person acted but the record keeps no actor (not the system). */
  actor_recorded: boolean
  replan_cause: ReplanCause | null
  /** SCRUM-120: the `id`s of the entries this one links to rather than repeats. */
  related_entry_ids: string[]
}

/** The caller may not read this event's history (AC6). */
export class EventHistoryForbiddenError extends Error {
  constructor() {
    super('This event’s history is not available to you.')
    this.name = 'EventHistoryForbiddenError'
  }
}

export async function getEventHistory(
  token: string,
  eventId: string,
): Promise<EventHistoryEntry[]> {
  const response = await fetch(`/api/event-requests/${eventId}/history`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (response.status === 403) throw new EventHistoryForbiddenError()
  if (!response.ok) throw new Error(`Could not load event history (${response.status})`)
  return (await response.json()) as EventHistoryEntry[]
}

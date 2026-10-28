import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  type EventHistoryEntry,
  EventHistoryForbiddenError,
  type HistoryAction,
  type HistorySource,
  getEventHistory,
  type ReplanCause,
} from '../api/eventHistory'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-88: one event's recorded actions, in the order the API returns them (oldest
 * first, ties already broken by the API). Each row shows the action, who did it ("System"
 * for a hold's expiry), when in Singapore time, the record it came from, and the outcome,
 * reason or other detail the record keeps. Who may read it, and which internal notes
 * they get, is decided by the API (ADR-0062); this component only shows what it is sent.
 */
export default function EventHistory({
  eventId,
  eventName,
}: {
  eventId: string
  eventName: string | null
}) {
  const { token } = useAuth()
  const history = useQuery({
    queryKey: ['event-requests', eventId, 'history', token],
    queryFn: () => getEventHistory(token ?? '', eventId),
    enabled: token !== null,
  })
  const index = byId(history.data ?? [])

  return (
    <div className="mt-2 rounded border border-slate-100 p-2">
      <p className="font-medium text-slate-500">Event history</p>
      {history.isPending && <p className="mt-1 text-sm">Loading history…</p>}
      {history.error instanceof EventHistoryForbiddenError && (
        <p className="mt-1 text-sm text-slate-500">{history.error.message}</p>
      )}
      {history.isError && !(history.error instanceof EventHistoryForbiddenError) && (
        <p role="alert" className="mt-1 text-sm text-red-600">
          Could not load history: {history.error.message}
        </p>
      )}
      {history.data?.length === 0 && (
        <p className="mt-1 text-sm text-slate-500">
          No history you can see for {eventName ?? eventId} yet.
        </p>
      )}
      {history.data && history.data.length > 0 && (
        <ol className="mt-1 space-y-2 text-sm text-slate-600">
          {history.data.map((entry) => (
            <HistoryRow key={entry.id} entry={entry} byId={index} />
          ))}
        </ol>
      )}
    </div>
  )
}

/**
 * SCRUM-88: the history behind a button, beside the assignment-history toggle. It mounts,
 * and so fetches, only once opened. It is offered only in lists the API already limits to
 * events the viewer may read, so the component itself holds no access rule.
 */
export function EventHistoryToggle({
  eventId,
  eventName,
}: {
  eventId: string
  eventName: string | null
}) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="text-sm text-slate-600 underline"
      >
        {open ? 'Hide event history' : 'View event history'}
      </button>
      {open && <EventHistory eventId={eventId} eventName={eventName} />}
    </div>
  )
}

function HistoryRow({
  entry,
  byId,
}: {
  entry: EventHistoryEntry
  byId: Map<string, EventHistoryEntry>
}) {
  // SCRUM-120: the entries this one links to are shown by name, never repeated in full.
  const related = entry.related_entry_ids.flatMap((id) => byId.get(id) ?? [])
  return (
    <li>
      {/* SCRUM-120: a person acted but the record keeps no actor; not "System" (ADR-0067). */}
      {entry.actor_recorded ? (
        <p>
          <span className="font-medium text-slate-800">{actionLabel(entry)}</span> by{' '}
          {actorLabel(entry)} at{' '}
          <time dateTime={entry.occurred_at}>{formatSingaporeTime(entry.occurred_at)}</time>
        </p>
      ) : (
        <p>
          <span className="font-medium text-slate-800">{actionLabel(entry)}</span> at{' '}
          <time dateTime={entry.occurred_at}>{formatSingaporeTime(entry.occurred_at)}</time> (actor
          not recorded)
        </p>
      )}
      {entry.replan_cause !== null && <p>Cause: {CAUSE_LABELS[entry.replan_cause]}</p>}
      {entry.new_coordinator_email !== null && (
        <p>
          {entry.previous_coordinator_email ?? 'No previous Coordinator'} →{' '}
          {entry.new_coordinator_email}
        </p>
      )}
      {entry.venue_name !== null && (
        <p>
          {entry.venue_name}
          {entry.session_label !== null && `, ${entry.session_label}`}
          {entry.session_start_at !== null && entry.session_end_at !== null && (
            <>
              ,{' '}
              <time dateTime={entry.session_start_at}>
                {formatSingaporeTime(entry.session_start_at)}
              </time>{' '}
              to{' '}
              <time dateTime={entry.session_end_at}>
                {formatSingaporeTime(entry.session_end_at)}
              </time>
            </>
          )}
        </p>
      )}
      {entry.equipment_type !== null && (
        <p>
          {entry.equipment_type}
          {entry.quantity !== null && ` × ${entry.quantity}`}
        </p>
      )}
      {entry.related_booking_id !== null && (
        <p>
          {entry.action === 'arrangement_cancelled' ? 'Replaced by' : 'Replaces'} arrangement{' '}
          {entry.related_booking_id}
        </p>
      )}
      {entry.affected_booking_ids.length > 0 && (
        <p>Affected arrangements: {entry.affected_booking_ids.join(', ')}</p>
      )}
      {/* SCRUM-119: only the fields the API's reader named, under its labels (ADR-0064). */}
      {entry.changes.map((change) => (
        <p key={change.field}>
          {change.label}: {change.old ?? '—'} → {change.new ?? '—'}
        </p>
      ))}
      {entry.hold_expires_at !== null && (
        <p>
          Held until{' '}
          <time dateTime={entry.hold_expires_at}>{formatSingaporeTime(entry.hold_expires_at)}</time>
        </p>
      )}
      {entry.reason !== null && <p>Reason: {entry.reason}</p>}
      {related.length > 0 && (
        <div>
          <p>{entry.action === 'event_cancelled' ? 'Released:' : 'Caused by:'}</p>
          <ul className="list-disc pl-5">
            {related.map((other) => (
              <li key={other.id}>{relatedLabel(other)}</li>
            ))}
          </ul>
        </div>
      )}
      {entry.note !== null && <p>Note: {entry.note}</p>}
      <p className="text-xs text-slate-400">
        Record: {SOURCE_LABELS[entry.source_type]} {entry.source_id}
      </p>
    </li>
  )
}

const ACTION_LABELS: Record<HistoryAction, string> = {
  draft_created: 'Draft created',
  submitted: 'Submitted for review',
  review_decided: 'Coordinator review',
  coordinator_assigned: 'Coordinator assigned',
  coordinator_reassigned: 'Coordinator reassigned',
  clarification_requested: 'Internal note',
  clarification_responded: 'Organiser response',
  venue_requested: 'Venue requested',
  venue_decided: 'Venue Staff decision',
  hold_created: 'Tentative hold placed',
  hold_confirmed: 'Hold confirmed',
  hold_expired: 'Hold expired',
  replacement_adopted: 'Replacement adopted',
  arrangement_cancelled: 'Venue arrangement cancelled',
  buffer_changed: 'Venue buffers changed',
  requirement_added: 'Equipment requirement added',
  requirement_updated: 'Equipment requirement changed',
  requirement_removed: 'Equipment requirement removed',
  equipment_reserved: 'Equipment reserved',
  reservation_flagged: 'Reservation flagged for reconsideration',
  reservation_released: 'Reservation released',
  event_confirmed: 'Event confirmed',
  returned_to_planning: 'Returned to planning',
  event_cancelled: 'Event cancelled',
}

const CAUSE_LABELS: Record<ReplanCause, string> = {
  change_request: 'a change request was approved',
  venue_closure: 'a venue closure',
  venue_cancellation: 'a venue change',
}

const SOURCE_LABELS: Record<HistorySource, string> = {
  event_request: 'event request',
  coordinator_assignment: 'assignment',
  clarification: 'internal note',
  venue_booking: 'venue booking',
  venue_buffer_change: 'venue buffer change',
  equipment_requirement_change: 'equipment requirement change',
  equipment_reservation: 'equipment reservation',
  safety_review: 'safety approval',
}

function byId(entries: EventHistoryEntry[]): Map<string, EventHistoryEntry> {
  return new Map(entries.map((entry) => [entry.id, entry]))
}

/** A linked entry in one line: what happened, and to which arrangement or equipment. */
function relatedLabel(entry: EventHistoryEntry): string {
  const what =
    entry.venue_name !== null
      ? [entry.venue_name, entry.session_label].filter((part) => part !== null).join(', ')
      : entry.equipment_type !== null
        ? `${entry.equipment_type}${entry.quantity !== null ? ` × ${entry.quantity}` : ''}`
        : null
  return what === null ? actionLabel(entry) : `${actionLabel(entry)}: ${what}`
}

/** A decision's outcome is part of what happened, so it is named with the action. */
function actionLabel(entry: EventHistoryEntry): string {
  const label = ACTION_LABELS[entry.action]
  return entry.outcome === null ? label : `${label}: ${entry.outcome}`
}

/** No actor id is the system; an id without an email is a missing user (ADR-0047). */
function actorLabel(entry: EventHistoryEntry): string {
  if (entry.actor_id === null) return 'System'
  return entry.actor_email ?? 'Unknown user'
}

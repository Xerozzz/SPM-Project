import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState } from 'react'

import {
  cancelVenueArrangement,
  EventRequestValidationError,
  startVenueChange,
  type VenueBooking,
  type VenueChange,
} from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import { hasReviewNote } from '../validation/eventRequestReview'

/**
 * SCRUM-109: confirm cancelling one arrangement, with a required reason. The API decides
 * (ADR-0056): a refusal is shown here with its message and nothing on the page changes.
 *
 * SCRUM-118: given `onVenueChanged`, the arrangement belongs to a Confirmed event, so
 * cancelling it is a venue change that returns the event to planning (ADR-0066). The
 * Coordinator is told what that does and has to tick that they understand before it can
 * be started; the tick is what is sent as `confirm_venue_change`.
 */
export default function CancelArrangementDialog({
  eventId,
  booking,
  venueName,
  onClose,
  onVenueChanged,
}: {
  eventId: string
  booking: VenueBooking
  venueName: string
  onClose: () => void
  onVenueChanged?: (change: VenueChange) => void
}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const [understood, setUnderstood] = useState(false)
  const reasonField = useRef<HTMLTextAreaElement>(null)
  const titleId = useId()
  const venueChange = onVenueChanged !== undefined
  const cancel = useMutation({
    mutationFn: async (): Promise<VenueChange | VenueBooking> =>
      venueChange
        ? startVenueChange(token ?? '', eventId, booking.id, reason)
        : cancelVenueArrangement(token ?? '', eventId, booking.id, reason),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['venue-bookings', eventId] })
      if (onVenueChanged && 'event_status' in result) onVenueChanged(result)
      onClose()
    },
  })

  useEffect(() => {
    reasonField.current?.focus()
  }, [])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={(key) => {
        if (key.key === 'Escape' && !cancel.isPending) onClose()
      }}
      className="mt-2 rounded border border-red-200 bg-red-50 p-3"
    >
      <h5 id={titleId} className="font-medium text-red-900">
        Cancel {booking.session_label} at {venueName}?
      </h5>
      <p className="mt-1">
        {formatSingaporeTime(booking.start_at)} to {formatSingaporeTime(booking.end_at)}. The venue
        is released and this cannot be undone.
      </p>
      {venueChange && (
        <p role="note" className="mt-2 rounded bg-amber-100 p-2 text-amber-900">
          This event is confirmed, so cancelling this arrangement starts a venue change. The event
          returns to planning, its safety approval stops counting, and new registrations are
          suspended. Existing registrations are kept.
        </p>
      )}
      <label className="mt-2 grid gap-1">
        Reason for cancelling
        <textarea
          ref={reasonField}
          value={reason}
          onChange={(change) => setReason(change.target.value)}
          required
          className="rounded border border-slate-300 p-2"
        />
      </label>
      {venueChange && (
        <label className="mt-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={understood}
            onChange={(change) => setUnderstood(change.target.checked)}
          />
          I understand this returns the event to planning
        </label>
      )}
      {cancel.error && (
        <p role="alert" className="mt-2 text-red-700">
          {cancel.error instanceof EventRequestValidationError
            ? cancel.error.problems.map((problem) => problem.reason).join('; ')
            : cancel.error.message}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={cancel.isPending}
          className="rounded border border-slate-300 bg-white px-2 py-1 disabled:opacity-50"
        >
          Keep arrangement
        </button>
        <button
          type="button"
          onClick={() => cancel.mutate()}
          disabled={!hasReviewNote(reason) || (venueChange && !understood) || cancel.isPending}
          className="rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
        >
          {cancel.isPending
            ? 'Cancelling…'
            : venueChange
              ? 'Start venue change'
              : 'Confirm cancellation'}
        </button>
      </div>
    </div>
  )
}

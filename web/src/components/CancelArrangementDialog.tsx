import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState } from 'react'

import {
  cancelVenueArrangement,
  EventRequestValidationError,
  type VenueBooking,
} from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import { hasReviewNote } from '../validation/eventRequestReview'

/**
 * SCRUM-109: confirm cancelling one arrangement, with a required reason. The API decides
 * (ADR-0056): a refusal is shown here with its message and nothing on the page changes.
 */
export default function CancelArrangementDialog({
  eventId,
  booking,
  venueName,
  onClose,
}: {
  eventId: string
  booking: VenueBooking
  venueName: string
  onClose: () => void
}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const reasonField = useRef<HTMLTextAreaElement>(null)
  const titleId = useId()
  const cancel = useMutation({
    mutationFn: () => cancelVenueArrangement(token ?? '', eventId, booking.id, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['venue-bookings', eventId] })
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
          disabled={!hasReviewNote(reason) || cancel.isPending}
          className="rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
        >
          {cancel.isPending ? 'Cancelling…' : 'Confirm cancellation'}
        </button>
      </div>
    </div>
  )
}

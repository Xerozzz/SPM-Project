import { useMutation, useQueryClient } from '@tanstack/react-query'

import type { VenueBooking } from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { adoptReplacement } from '../api/venueReplacements'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-133: adopt an approved replacement. The original is cancelled and the link kept.
 * The API decides what may be adopted. This only hides the button where it never could.
 */
export default function AdoptReplacement({
  eventId,
  replacement,
  original,
}: {
  eventId: string
  replacement: VenueBooking
  original: VenueBooking | undefined
}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const adopt = useMutation({
    mutationFn: () => adoptReplacement(token ?? '', eventId, replacement.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['venue-bookings', eventId] })
    },
  })

  if (replacement.adopted_at) {
    return (
      <p className="mt-2 text-sky-900" role="status">
        Adopted on {formatSingaporeTime(replacement.adopted_at)}. The original booking was
        cancelled.
      </p>
    )
  }
  const approved = ['tentative', 'confirmed'].includes(replacement.status)
  const originalLive = original && ['tentative', 'confirmed'].includes(original.status)
  if (!approved || !originalLive) return null

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => adopt.mutate()}
        disabled={adopt.isPending}
        aria-label={`Adopt this replacement for ${replacement.session_label}`}
        className="rounded border border-sky-700 px-2 py-1 text-sky-900"
      >
        Adopt this replacement
      </button>
      <span className="ml-2 text-slate-500">
        The original booking will be cancelled. The event is not reconfirmed.
      </span>
      {adopt.isError && (
        <p role="alert" className="mt-1 text-red-700">
          {adopt.error.message}
        </p>
      )}
    </div>
  )
}

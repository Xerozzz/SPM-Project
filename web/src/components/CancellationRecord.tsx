import { useQuery } from '@tanstack/react-query'

import { readCancellation } from '../api/eventCancellation'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/** SCRUM-115 AC3: when a cancelled event was cancelled and why. */
export default function CancellationRecord({ eventId }: { eventId: string }) {
  const { token } = useAuth()
  const record = useQuery({
    queryKey: ['event-cancellation', eventId, token],
    queryFn: () => readCancellation(token ?? '', eventId),
    enabled: token !== null,
  })

  if (record.isPending) return <p className="mt-2 text-sm">Loading…</p>
  if (record.isError) {
    return (
      <p role="alert" className="mt-2 text-sm text-red-600">
        {record.error.message}
      </p>
    )
  }
  const { cancelled_at, cancellation_reason } = record.data
  return (
    <p className="mt-1 text-sm text-red-700">
      {cancelled_at && <>Cancelled {formatSingaporeTime(cancelled_at)}. </>}
      {cancellation_reason && <>Reason: {cancellation_reason}</>}
    </p>
  )
}

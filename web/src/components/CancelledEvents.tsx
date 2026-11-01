import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { listCancelledEvents } from '../api/eventCancellation'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-88 AC6: cancelled events leave every working list, so the assigned Coordinator
 * and Leads open their history here. Read-only. A Lead's list already holds every
 * cancelled event, so a Lead who is also a Coordinator gets that one list, not both.
 *
 * A "View cancelled event" notification passes the event as `targetEventId`. That event is
 * no longer in the working list above, so it is brought into view here with its history
 * open, rather than leaving the viewer on the queue wondering where it went.
 */
export default function CancelledEvents({
  targetEventId = null,
}: {
  targetEventId?: string | null
}) {
  const { token, hasRole } = useAuth()
  const scope = hasRole('coordinator_lead') ? 'all' : 'assigned'
  const events = useQuery({
    queryKey: ['event-requests', 'cancelled', scope, token],
    queryFn: () => listCancelledEvents(token ?? '', scope),
    enabled: token !== null,
  })
  const target = useRef<HTMLElement>(null)
  const targetListed = events.data?.some((event) => event.id === targetEventId) ?? false
  useEffect(() => {
    if (!targetListed) return
    target.current?.scrollIntoView?.({ block: 'start' })
    target.current?.focus()
  }, [targetListed, targetEventId])
  if (!events.data || events.data.length === 0) return null
  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Cancelled events</h2>
      {events.data.map((event) => (
        <article
          key={event.id}
          ref={event.id === targetEventId ? target : undefined}
          tabIndex={event.id === targetEventId ? -1 : undefined}
          aria-current={event.id === targetEventId ? 'true' : undefined}
          className={`mt-3 rounded border p-3 ${event.id === targetEventId ? 'border-red-300 bg-red-50/40' : 'border-slate-100'}`}
        >
          <h3 className="font-medium">{event.name ?? 'Untitled event'}</h3>
          <p className="mt-1 text-sm text-red-700">
            {event.cancelled_at && <>Cancelled {formatSingaporeTime(event.cancelled_at)}. </>}
            {event.cancellation_reason && <>Reason: {event.cancellation_reason}</>}
          </p>
          {/* SCRUM-88: the API lists only events whose history this viewer may read. */}
          <EventHistoryToggle
            eventId={event.id}
            eventName={event.name}
            initiallyOpen={event.id === targetEventId}
          />
        </article>
      ))}
    </section>
  )
}

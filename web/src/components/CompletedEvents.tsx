import { useQuery } from '@tanstack/react-query'

import { listCompletedEvents } from '../api/eventCompletion'
import { useAuth } from '../auth/useAuth'
import ClosureRecord from './ClosureRecord'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-86: the Coordinator's completed events, each with its correctable closure record.
 * A completed event leaves the active list, so it is shown here instead.
 */
export default function CompletedEvents() {
  const { token } = useAuth()
  const events = useQuery({
    queryKey: ['event-requests', 'completed', token],
    queryFn: () => listCompletedEvents(token ?? ''),
    enabled: token !== null,
  })
  if (!events.data || events.data.length === 0) return null
  return (
    <section>
      {events.data.map((event) => (
        <article key={event.id} className="mt-3 rounded border border-slate-100 p-3">
          <h3 className="font-medium">{event.name ?? 'Untitled event'}</h3>
          <ClosureRecord eventId={event.id} canCorrect />
          {/* SCRUM-88: this list holds only completed events assigned to the viewer. */}
          <EventHistoryToggle eventId={event.id} eventName={event.name} />
        </article>
      ))}
    </section>
  )
}

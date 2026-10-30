import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { listCompletedEvents } from '../api/eventCompletion'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import ClosureRecord from './ClosureRecord'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-86: the Coordinator's completed events, each with its correctable closure record.
 * A completed event leaves the active list, so it is shown here instead.
 */
export default function CompletedEvents() {
  const { token } = useAuth()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const events = useQuery({
    queryKey: ['event-requests', 'completed', token],
    queryFn: () => listCompletedEvents(token ?? ''),
    enabled: token !== null,
  })
  if (!events.data || events.data.length === 0) return null
  const selectedEvent = events.data.find((event) => event.id === selectedId)
  return (
    <section>
      {selectedEvent ? (
        <div>
          <button type="button" className="cs-button-secondary" onClick={() => setSelectedId(null)}>
            ← Back to Completed Events
          </button>
          <h2 className="mt-5">{selectedEvent.name ?? 'Untitled event'}</h2>
          <CompletedEventDetails event={selectedEvent} />
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {events.data.map((event) => (
            <li
              key={event.id}
              className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5"
            >
              <span className="inline-flex self-start rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800">
                Completed
              </span>
              <h3 className="mt-3 break-words text-lg font-semibold tracking-normal">
                {event.name ?? 'Untitled event'}
              </h3>
              <dl className="mt-4 flex-1 space-y-3 text-sm">
                <div>
                  <dt className="text-xs text-slate-500">Schedule · Singapore time</dt>
                  <dd className="mt-1">
                    {event.start_at ? formatSingaporeTime(event.start_at) : 'Date to be confirmed'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Venue preference</dt>
                  <dd className="mt-1 break-words">{event.venue_requirement || 'Not specified'}</dd>
                </div>
              </dl>
              <button
                type="button"
                className="cs-button-secondary mt-5 w-full"
                onClick={() => setSelectedId(event.id)}
              >
                View details →
              </button>
              {/* SCRUM-88: this list holds only completed events assigned to the viewer. */}
              <div className="mt-4">
                <EventHistoryToggle eventId={event.id} eventName={event.name} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function CompletedEventDetails({
  event,
}: {
  event: Awaited<ReturnType<typeof listCompletedEvents>>[number]
}) {
  return (
    <div className="mt-5 space-y-5">
      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        <Detail label="Purpose" value={event.purpose} />
        <Detail label="Description" value={event.description} />
        <Detail
          label="Schedule"
          value={
            event.start_at && event.end_at
              ? `${formatSingaporeTime(event.start_at)} – ${formatSingaporeTime(event.end_at)}`
              : 'Date to be confirmed'
          }
        />
        <Detail label="Expected attendance" value={event.expected_attendance?.toString() ?? null} />
        <Detail label="Venue preference" value={event.venue_requirement} />
        <Detail label="Accessibility" value={event.accessibility_requirement} />
        <Detail label="Equipment requested" value={event.equipment_requirement} />
        <Detail label="Layout" value={event.layout_requirement} />
        <Detail label="Registration" value={event.registration_requirement} />
      </dl>
      <ClosureRecord eventId={event.id} canCorrect />
      <EventHistoryToggle eventId={event.id} eventName={event.name} />
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 whitespace-pre-wrap break-words">{value || 'Not specified'}</dd>
    </div>
  )
}

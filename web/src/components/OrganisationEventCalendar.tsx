import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { type EventCalendarEntry, listOrganisationCalendar } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-87: organisation planning visibility. SCRUM-112 (ADR-0039): selecting an entry shows
 * only the calendar fields already loaded, and never fetches the full request, which the API
 * refuses to anyone but its owner.
 */
export default function OrganisationEventCalendar() {
  const { token } = useAuth()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const calendar = useQuery({
    queryKey: ['organisation-calendar', token],
    queryFn: () => listOrganisationCalendar(token ?? ''),
    enabled: token !== null,
  })
  const selected = calendar.data?.find((event) => event.id === selectedId)

  return (
    <section aria-labelledby="organisation-calendar-heading" className="mt-6 border-t pt-4">
      <h2 id="organisation-calendar-heading" className="font-medium">
        Organisation calendar
      </h2>
      {calendar.isPending && <p role="status">Loading organisation calendar...</p>}
      {calendar.isError && <p role="alert">{calendar.error.message}</p>}
      {calendar.isSuccess && calendar.data.length === 0 && <p>No dated events.</p>}
      <ol className="mt-2 divide-y divide-slate-200">
        {calendar.data?.map((event) => {
          const title = event.name || 'Untitled event'
          return (
            <li key={event.id} className="py-2 text-sm">
              <button
                type="button"
                aria-label={`View ${title} details`}
                aria-expanded={selectedId === event.id}
                onClick={() => setSelectedId(event.id)}
                className="w-full p-1 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <span className="block break-words font-medium">{title}</span>
                <span className="block">
                  <time dateTime={event.start_at}>{formatDateTime(event.start_at)}</time>
                  {' to '}
                  <time dateTime={event.end_at}>{formatDateTime(event.end_at)}</time>
                </span>
                <span className="block capitalize">{event.status}</span>
              </button>
            </li>
          )
        })}
      </ol>
      {selected && <CalendarEntryDetails entry={selected} />}
    </section>
  )
}

function CalendarEntryDetails({ entry }: { entry: EventCalendarEntry }) {
  return (
    <article aria-label="Event calendar details" className="mt-4 border-t border-slate-200 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium">{entry.name || 'Untitled event'}</h3>
        <span className="text-sm capitalize text-slate-500">{entry.status}</span>
      </div>
      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="font-medium text-slate-600">Start date and time</dt>
          <dd>{formatDateTime(entry.start_at)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">End date and time</dt>
          <dd>{formatDateTime(entry.end_at)}</dd>
        </div>
      </dl>
      <p className="mt-3 text-sm text-slate-500">Calendar details only</p>
    </article>
  )
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString()
}

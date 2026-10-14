import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { type EventRequest, getEventRequest, listOrganisationCalendar } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/** SCRUM-87: organisation planning visibility with a read-only request detail view. */
export default function OrganisationEventCalendar() {
  const { token } = useAuth()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const calendar = useQuery({
    queryKey: ['organisation-calendar', token],
    queryFn: () => listOrganisationCalendar(token ?? ''),
    enabled: token !== null,
  })
  const detail = useQuery({
    queryKey: ['organisation-calendar', 'detail', token, selectedId],
    queryFn: () => getEventRequest(token ?? '', selectedId ?? ''),
    enabled: token !== null && selectedId !== null,
  })

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
      {selectedId && detail.isPending && <p role="status">Loading event details...</p>}
      {selectedId && detail.isError && <p role="alert">{detail.error.message}</p>}
      {detail.data && <ReadOnlyDetails request={detail.data} />}
    </section>
  )
}

function ReadOnlyDetails({ request }: { request: EventRequest }) {
  return (
    <article aria-label="Event request details" className="mt-4 border-t border-slate-200 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium">{request.name ?? 'Untitled event'}</h3>
        <span className="text-sm capitalize text-slate-500">{request.status}</span>
      </div>
      <dl className="mt-3 space-y-2 text-sm">
        <Detail label="Purpose" value={request.purpose} />
        <Detail label="Description" value={request.description} />
        <Detail label="Start date and time" value={formatOptionalDateTime(request.start_at)} />
        <Detail label="End date and time" value={formatOptionalDateTime(request.end_at)} />
        <Detail label="Expected attendance" value={request.expected_attendance?.toString()} />
        <Detail label="Venue requirement" value={request.venue_requirement} />
        <Detail label="Accessibility requirement" value={request.accessibility_requirement} />
        <Detail label="Equipment requirement" value={request.equipment_requirement} />
        <Detail label="Layout requirement" value={request.layout_requirement} />
        <Detail label="Registration requirement" value={request.registration_requirement} />
      </dl>
      <p className="mt-3 text-sm text-slate-500">Read-only organisation view</p>
    </article>
  )
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="font-medium text-slate-600">{label}</dt>
      <dd className="break-words">{value || 'Not provided'}</dd>
    </div>
  )
}

function formatOptionalDateTime(value: string | null): string {
  return value === null ? 'Not provided' : formatDateTime(value)
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString()
}

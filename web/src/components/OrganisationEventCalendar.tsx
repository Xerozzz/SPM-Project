import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  type EventCalendarEntry,
  listMyEventRequests,
  listOrganisationCalendar,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-87: organisation planning visibility. SCRUM-112 (ADR-0039): selecting an entry shows
 * only the calendar fields already loaded, and never fetches the full request, which the API
 * refuses to anyone but its owner.
 */
export default function OrganisationEventCalendar({
  onOpenOwnEvent = () => {},
}: {
  /** Opens the existing full details view only after the event is confirmed as the caller's. */
  onOpenOwnEvent?: (eventId: string) => void
} = {}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [month, setMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  )
  const calendar = useQuery({
    queryKey: ['organisation-calendar', token],
    queryFn: () => listOrganisationCalendar(token ?? ''),
    enabled: token !== null,
  })
  const selected = calendar.data?.find((event) => event.id === selectedId)

  async function openEvent(event: EventCalendarEntry) {
    try {
      // The caller's list is the only safe ownership source: the calendar projection must not
      // disclose an organiser id, and a peer's full request endpoint is deliberately forbidden.
      const ownRequests = await queryClient.fetchQuery({
        queryKey: ['event-requests', 'mine', token],
        queryFn: () => listMyEventRequests(token ?? ''),
      })
      if (ownRequests.some((request) => request.id === event.id)) {
        onOpenOwnEvent(event.id)
        return
      }
    } catch {
      // The calendar projection remains useful if refreshing the caller's own list fails.
    }
    setSelectedId(event.id)
  }
  const eventsByDay = (calendar.data ?? []).reduce<Record<string, EventCalendarEntry[]>>(
    (groups, event) => {
      const cursor = new Date(event.start_at)
      const end = new Date(event.end_at)
      cursor.setHours(0, 0, 0, 0)
      end.setHours(0, 0, 0, 0)
      while (cursor <= end) {
        const key = dateKey(cursor)
        ;(groups[key] ??= []).push(event)
        cursor.setDate(cursor.getDate() + 1)
      }
      return groups
    },
    {},
  )
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1)
  const calendarDays = Array.from(
    {
      length: firstDay.getDay() + new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate(),
    },
    (_, index) =>
      index < firstDay.getDay()
        ? null
        : new Date(month.getFullYear(), month.getMonth(), index - firstDay.getDay() + 1),
  )

  return (
    <section aria-label="Organisation calendar">
      {calendar.isPending && <p role="status">Loading organisation calendar...</p>}
      {calendar.isError && <p role="alert">{calendar.error.message}</p>}
      {calendar.isSuccess && calendar.data.length === 0 && <p>No dated events.</p>}
      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous month"
          onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
          className="cs-button-secondary"
        >
          ‹
        </button>
        <h3 className="text-2xl font-medium tracking-[-0.04em] text-[#202124]">
          {month.toLocaleString(undefined, { month: 'long', year: 'numeric' })}
        </h3>
        <button
          type="button"
          aria-label="Next month"
          onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
          className="cs-button-secondary"
        >
          ›
        </button>
      </div>
      <div className="mt-4 grid grid-cols-7 gap-2 text-xs font-medium tracking-[-0.02em] text-slate-500">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
          <span key={day} className="px-2 py-1">
            {day}
          </span>
        ))}
      </div>
      <ol className="grid grid-cols-7 gap-2">
        {calendarDays.map((day, index) => {
          if (!day)
            return (
              <li
                key={`empty-${index}`}
                className="min-h-24 rounded-xl bg-slate-50/60"
                aria-hidden="true"
              />
            )
          const events = eventsByDay[dateKey(day)] ?? []
          return (
            <li
              key={dateKey(day)}
              className="min-h-24 rounded-xl border border-slate-100 bg-white p-2 text-sm"
            >
              <span className="block px-1 text-xs text-slate-400">{day.getDate()}</span>
              {events.map((event) => {
                const title = `${event.name || 'Untitled event'}${dayNumber(event, day) ? ` (${dayNumber(event, day)})` : ''}`
                return (
                  <button
                    key={event.id}
                    type="button"
                    aria-label={`View ${title} details`}
                    aria-expanded={selectedId === event.id}
                    onClick={() => void openEvent(event)}
                    className="w-full rounded-lg p-2 text-left transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  >
                    <span className="block break-words font-medium tracking-[-0.02em] text-[#202124]">
                      {title}
                    </span>
                    <span
                      className={`mt-1 inline-flex rounded-md px-2 py-0.5 text-xs font-medium capitalize ${statusStyle(event.status)}`}
                    >
                      {event.status}
                    </span>
                  </button>
                )
              })}
            </li>
          )
        })}
      </ol>
      {selected && <CalendarEntryDetails entry={selected} />}
    </section>
  )
}

function dateKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function dayNumber(event: EventCalendarEntry, day: Date): number | null {
  const start = new Date(event.start_at)
  const end = new Date(event.end_at)
  start.setHours(0, 0, 0, 0)
  end.setHours(0, 0, 0, 0)
  if (start.getTime() === end.getTime()) return null
  return Math.round((day.getTime() - start.getTime()) / 86_400_000) + 1
}

function statusStyle(status: EventCalendarEntry['status']): string {
  return {
    draft: 'bg-slate-100 text-slate-700',
    submitted: 'bg-amber-50 text-amber-800',
    approved: 'bg-sky-50 text-sky-800',
    rejected: 'bg-red-50 text-red-800',
    confirmed: 'bg-emerald-50 text-emerald-800',
    completed: 'bg-indigo-50 text-indigo-800',
    cancelled: 'bg-slate-200 text-slate-700',
  }[status]
}

function detailStyle(status: EventCalendarEntry['status']): string {
  return {
    draft: 'border-slate-200 bg-slate-100',
    submitted: 'border-amber-100 bg-amber-50',
    approved: 'border-sky-100 bg-sky-50',
    rejected: 'border-red-100 bg-red-50',
    confirmed: 'border-emerald-100 bg-emerald-50',
    completed: 'border-indigo-100 bg-indigo-50',
    cancelled: 'border-red-100 bg-red-50',
  }[status]
}

function CalendarEntryDetails({ entry }: { entry: EventCalendarEntry }) {
  return (
    <article
      aria-label="Event calendar details"
      className={`mt-4 rounded-lg border p-4 ${detailStyle(entry.status)}`}
    >
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

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import {
  type AttendeeEvent,
  type EventRegistration,
  type RegistrationStatus,
  type RegistrationSubmission,
  listOpenEvents,
  readMyRegistration,
  submitRegistration,
  withdrawRegistration,
} from '../api/eventRegistrations'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

type RegistrationFilter = RegistrationStatus | 'available' | 'all'
type RegistrationEntry = { event: AttendeeEvent; registration: EventRegistration | null }

const FILTER_ORDER: RegistrationFilter[] = [
  'available',
  'pending',
  'waitlisted',
  'accepted',
  'withdrawn',
  'cancelled',
]
const FILTER_TITLES: Record<RegistrationFilter, string> = {
  all: 'All events',
  available: 'Available',
  pending: 'Pending',
  waitlisted: 'Waitlisted',
  accepted: 'Accepted',
  withdrawn: 'Withdrawn',
  cancelled: 'Cancelled',
}

/** Compact attendee-registration summaries; API rules remain authoritative. */
export default function AttendeeRegistrations() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [selectedFilter, setSelectedFilter] = useState<RegistrationFilter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const openedFrom = useRef<string | null>(null)
  const detailsHeading = useRef<HTMLHeadingElement>(null)
  const events = useQuery({
    queryKey: ['attendee-events', token],
    queryFn: () => listOpenEvents(token ?? ''),
    enabled: token !== null,
  })
  const registrations = useQueries({
    queries: (events.data ?? []).map((event) => ({
      queryKey: ['attendee-registration', event.id, token],
      queryFn: () => readMyRegistration(token ?? '', event.id),
      enabled: token !== null,
    })),
  })
  const entries: RegistrationEntry[] = (events.data ?? []).map((event, index) => ({
    event,
    registration: registrations[index]?.data ?? null,
  }))
  const registrationsLoading = registrations.some((registration) => registration.isPending)
  const groupedEntries = FILTER_ORDER.map((filter) => ({
    filter,
    entries: entries.filter((entry) => entryFilter(entry) === filter),
  })).filter((group) => group.entries.length > 0)
  const visibleEntries = entries.filter(
    (entry) =>
      (selectedId ? entry.event.id === selectedId : true) &&
      (selectedFilter === 'all' || entryFilter(entry) === selectedFilter),
  )

  useEffect(() => {
    if (selectedId) detailsHeading.current?.focus()
    else document.getElementById(openedFrom.current ?? '')?.focus()
  }, [selectedId])

  const submit = useMutation({
    mutationFn: ({ eventId, values }: { eventId: string; values: RegistrationSubmission }) =>
      submitRegistration(token ?? '', eventId, values),
    onSuccess: (_registration, { eventId }) =>
      void client.invalidateQueries({ queryKey: ['attendee-registration', eventId, token] }),
  })
  const withdraw = useMutation({
    mutationFn: (eventId: string) => withdrawRegistration(token ?? '', eventId),
    onSuccess: (_registration, eventId) =>
      void client.invalidateQueries({ queryKey: ['attendee-registration', eventId, token] }),
  })

  return (
    <section aria-label="Event registration">
      {selectedId ? (
        <button type="button" className="cs-button-secondary" onClick={() => setSelectedId(null)}>
          ← Back to registrations
        </button>
      ) : null}
      {(events.isPending || registrationsLoading) && (
        <p className="mt-2 text-sm text-slate-500">Loading events…</p>
      )}
      {events.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load events.
        </p>
      )}
      {registrations.some((registration) => registration.isError) && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load a registration.
        </p>
      )}
      {events.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No events are available.</p>
      )}
      {entries.length > 0 && !registrationsLoading && (
        <div className="mt-5">
          {!selectedId && (
            <div
              role="group"
              aria-label="Filter registrations by status"
              className="flex gap-2 overflow-x-auto border-b border-slate-200 pb-3"
            >
              {[{ filter: 'all' as const, entries }, ...groupedEntries].map((group) => (
                <button
                  key={group.filter}
                  type="button"
                  aria-pressed={selectedFilter === group.filter}
                  onClick={() => setSelectedFilter(group.filter)}
                  className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${selectedFilter === group.filter ? 'bg-[#202124] text-white' : 'bg-white text-slate-600 hover:bg-slate-100'}`}
                >
                  {FILTER_TITLES[group.filter]}{' '}
                  <span className="ml-1 opacity-70">{group.entries.length}</span>
                </button>
              ))}
            </div>
          )}
          {visibleEntries.length === 0 && (
            <p className="py-8 text-sm text-slate-500">
              No registrations in this status. Choose All events to see the rest.
            </p>
          )}
          <ul className={`mt-5 grid gap-4 ${selectedId ? '' : 'md:grid-cols-2 xl:grid-cols-3'}`}>
            {visibleEntries.map((entry) => (
              <li
                key={entry.event.id}
                className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5"
              >
                <StatusLabel filter={entryFilter(entry)} />
                {selectedId ? (
                  <h2 ref={detailsHeading} tabIndex={-1} className="mt-3 break-words">
                    {titleOf(entry.event)}
                  </h2>
                ) : (
                  <h3 className="mt-3 break-words text-lg font-semibold tracking-normal">
                    {titleOf(entry.event)}
                  </h3>
                )}
                <dl className="mt-4 flex-1 space-y-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500">Schedule · Singapore time</dt>
                    <dd className="mt-1">
                      {entry.event.start_at
                        ? formatSingaporeTime(entry.event.start_at)
                        : 'Date to be confirmed'}
                    </dd>
                  </div>
                  {selectedId && entry.event.description && (
                    <div>
                      <dt className="text-xs text-slate-500">About this event</dt>
                      <dd className="mt-1 whitespace-pre-wrap break-words">
                        {entry.event.description}
                      </dd>
                    </div>
                  )}
                </dl>
                {selectedId ? (
                  <RegistrationDetails
                    event={entry.event}
                    registration={entry.registration}
                    submitting={submit.isPending}
                    withdrawing={withdraw.isPending}
                    onSubmit={(values) => submit.mutate({ eventId: entry.event.id, values })}
                    onWithdraw={() => withdraw.mutate(entry.event.id)}
                  />
                ) : (
                  <button
                    type="button"
                    id={`view-registration-${entry.event.id}`}
                    className="cs-button-secondary mt-5 w-full"
                    aria-label={`View details for ${titleOf(entry.event)}`}
                    onClick={(event) => {
                      openedFrom.current = event.currentTarget.id
                      setSelectedId(entry.event.id)
                    }}
                  >
                    View details →
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {submit.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {submit.error.message}
        </p>
      )}
      {withdraw.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {withdraw.error.message}
        </p>
      )}
    </section>
  )
}

function RegistrationDetails({
  event,
  registration,
  submitting,
  withdrawing,
  onSubmit,
  onWithdraw,
}: {
  event: AttendeeEvent
  registration: EventRegistration | null
  submitting: boolean
  withdrawing: boolean
  onSubmit: (values: RegistrationSubmission) => void
  onWithdraw: () => void
}) {
  const [values, setValues] = useState({
    full_name: '',
    age: '',
    phone_number: '',
    dietary_accessibility_notes: '',
  })
  const [errors, setErrors] = useState<Partial<Record<keyof RegistrationSubmission, string>>>({})
  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      {registration && (
        <p className="text-sm" role="status">
          Registration status: {label(registration.status)}
        </p>
      )}
      {registration && canWithdraw(registration.status) && (
        <button
          type="button"
          disabled={withdrawing}
          onClick={onWithdraw}
          className="cs-button-secondary mt-3 disabled:opacity-50"
        >
          Withdraw registration
        </button>
      )}
      {(!registration || registration.status === 'withdrawn') && event.intake_open && (
        <form
          className="mt-3 space-y-3"
          onSubmit={(submit) => {
            submit.preventDefault()
            const nextErrors = validate(values)
            if (Object.keys(nextErrors).length > 0) {
              setErrors(nextErrors)
              return
            }
            setErrors({})
            onSubmit({
              full_name: values.full_name,
              age: Number(values.age),
              phone_number: values.phone_number,
              dietary_accessibility_notes: values.dietary_accessibility_notes || null,
            })
          }}
        >
          <Field label="Full name" error={errors.full_name}>
            <input
              value={values.full_name}
              onChange={(change) => setValues({ ...values, full_name: change.target.value })}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Age" error={errors.age}>
            <input
              type="number"
              min="0"
              value={values.age}
              onChange={(change) => setValues({ ...values, age: change.target.value })}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Phone number" error={errors.phone_number}>
            <input
              type="tel"
              value={values.phone_number}
              onChange={(change) => setValues({ ...values, phone_number: change.target.value })}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </Field>
          <Field label="Dietary or accessibility notes (optional)">
            <textarea
              value={values.dietary_accessibility_notes}
              onChange={(change) =>
                setValues({ ...values, dietary_accessibility_notes: change.target.value })
              }
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </Field>
          <button type="submit" disabled={submitting} className="cs-button disabled:opacity-50">
            Register
          </button>
        </form>
      )}
    </div>
  )
}

function StatusLabel({ filter }: { filter: Exclude<RegistrationFilter, 'all'> }) {
  const styles: Record<Exclude<RegistrationFilter, 'all'>, string> = {
    available: 'bg-sky-50 text-sky-800',
    pending: 'bg-amber-50 text-amber-800',
    waitlisted: 'bg-violet-50 text-violet-800',
    accepted: 'bg-emerald-50 text-emerald-800',
    withdrawn: 'bg-slate-100 text-slate-700',
    cancelled: 'bg-slate-200 text-slate-700',
  }
  return (
    <span
      className={`inline-flex self-start rounded-md px-2 py-0.5 text-xs font-medium ${styles[filter]}`}
    >
      {filter === 'available' ? 'Open for registration' : label(filter)}
    </span>
  )
}

function entryFilter(entry: RegistrationEntry): Exclude<RegistrationFilter, 'all'> {
  return entry.registration?.status ?? 'available'
}
function titleOf(event: AttendeeEvent): string {
  return event.name ?? 'Untitled event'
}
function label(status: Exclude<RegistrationFilter, 'available' | 'all'>): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}
function canWithdraw(status: RegistrationStatus) {
  return status === 'pending' || status === 'waitlisted' || status === 'accepted'
}
function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <label className="block text-sm">
      {label}
      {children}
      {error && (
        <span role="alert" className="block text-red-600">
          {error}
        </span>
      )}
    </label>
  )
}
function validate(values: { full_name: string; age: string; phone_number: string }) {
  const errors: Partial<Record<keyof RegistrationSubmission, string>> = {}
  if (!values.full_name.trim()) errors.full_name = 'Full name is required.'
  if (!/^\d+$/.test(values.age)) errors.age = 'Age must be a whole number.'
  if (!values.phone_number.trim()) errors.phone_number = 'Phone number is required.'
  return errors
}

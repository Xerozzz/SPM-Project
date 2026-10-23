import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  type RegistrationSubmission,
  listOpenEvents,
  readMyRegistration,
  submitRegistration,
} from '../api/eventRegistrations'
import { useAuth } from '../auth/useAuth'

/** Minimal attendee intake: identity is the signed-in account, not browser input. */
export default function AttendeeRegistrations() {
  const { token } = useAuth()
  const client = useQueryClient()
  const events = useQuery({
    queryKey: ['attendee-events', token],
    queryFn: () => listOpenEvents(token ?? ''),
    enabled: token !== null,
  })
  const submit = useMutation({
    mutationFn: ({ eventId, values }: { eventId: string; values: RegistrationSubmission }) =>
      submitRegistration(token ?? '', eventId, values),
    onSuccess: (_registration, { eventId }) =>
      void Promise.all([
        client.invalidateQueries({ queryKey: ['attendee-registration', eventId, token] }),
        client.invalidateQueries({ queryKey: ['attendee-events', token] }),
      ]),
  })

  return (
    <section
      className="mt-6 rounded-lg border border-slate-200 p-4"
      aria-label="Event registration"
    >
      <h2 className="font-medium">Open events</h2>
      <p className="mt-1 text-sm text-slate-500">
        Your signed-in account is used for registration.
      </p>
      {events.isPending && <p className="mt-2 text-sm text-slate-500">Loading events…</p>}
      {events.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load open events.
        </p>
      )}
      {events.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No events are open for registration.</p>
      )}
      <div className="mt-3 space-y-3">
        {events.data?.map((event) => (
          <EventCard
            key={event.id}
            event={event}
            token={token ?? ''}
            submitting={submit.isPending}
            onSubmit={(eventId, values) => submit.mutate({ eventId, values })}
          />
        ))}
      </div>
      {submit.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {submit.error.message}
        </p>
      )}
    </section>
  )
}

function EventCard({
  event,
  token,
  submitting,
  onSubmit,
}: {
  event: Awaited<ReturnType<typeof listOpenEvents>>[number]
  token: string
  submitting: boolean
  onSubmit: (eventId: string, values: RegistrationSubmission) => void
}) {
  const [values, setValues] = useState({
    full_name: '',
    age: '',
    phone_number: '',
    dietary_accessibility_notes: '',
  })
  const [errors, setErrors] = useState<Partial<Record<keyof RegistrationSubmission, string>>>({})
  const registration = useQuery({
    queryKey: ['attendee-registration', event.id, token],
    queryFn: () => readMyRegistration(token, event.id),
  })
  return (
    <article className="rounded border border-slate-200 p-3">
      <h3 className="font-medium">{event.name ?? 'Untitled event'}</h3>
      {event.description && <p className="mt-1 text-sm text-slate-600">{event.description}</p>}
      {event.start_at && (
        <p className="mt-1 text-sm text-slate-500">
          Starts {new Date(event.start_at).toLocaleString()}
        </p>
      )}
      {registration.data ? (
        <p className="mt-2 text-sm" role="status">
          Registration status: {label(registration.data.status)}
        </p>
      ) : (
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
            onSubmit(event.id, {
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
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Register
          </button>
        </form>
      )}
    </article>
  )
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

function label(status: 'pending' | 'waitlisted' | 'accepted' | 'withdrawn' | 'cancelled') {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { listOpenEvents, readMyRegistration, submitRegistration } from '../api/eventRegistrations'
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
    mutationFn: (eventId: string) => submitRegistration(token ?? '', eventId),
    onSuccess: (_registration, eventId) =>
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
            onSubmit={submit.mutate}
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
  onSubmit: (eventId: string) => void
}) {
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
        <button
          type="button"
          disabled={submitting}
          onClick={() => onSubmit(event.id)}
          className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Register
        </button>
      )}
    </article>
  )
}

function label(status: 'pending' | 'waitlisted' | 'accepted' | 'withdrawn' | 'cancelled') {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

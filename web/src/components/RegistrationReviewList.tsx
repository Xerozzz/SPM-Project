import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { decideRegistration, listEventRegistrations, type RegistrationStatus } from '../api/eventRegistrations'
import { useAuth } from '../auth/useAuth'

/** SCRUM-114's ordered list, with SCRUM-134's owner-only manual decisions. */
export default function RegistrationReviewList({
  eventId,
  canDecide = false,
}: {
  eventId: string
  canDecide?: boolean
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [notes, setNotes] = useState<Record<string, string>>({})
  const registrations = useQuery({
    queryKey: ['event-requests', eventId, 'registrations', token],
    queryFn: () => listEventRegistrations(token ?? '', eventId),
    enabled: token !== null,
  })
  const decision = useMutation({
    mutationFn: ({ id, expectedStatus, status }: { id: string; expectedStatus: RegistrationStatus; status: 'accepted' | 'waitlisted' }) =>
      decideRegistration(token ?? '', eventId, id, expectedStatus, status, notes[id] || null),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['event-requests', eventId, 'registrations', token] }),
  })

  return (
    <section className="mt-3 rounded border border-slate-200 p-3" aria-label="Registrations">
      <h4 className="text-sm font-medium">Registrations</h4>
      {registrations.isPending && <p className="mt-1 text-sm">Loading registrations…</p>}
      {registrations.isError && (
        <p role="alert" className="mt-1 text-sm text-red-600">
          Could not load registrations: {registrations.error.message}
        </p>
      )}
      {registrations.data?.length === 0 && (
        <p className="mt-1 text-sm text-slate-500">No registrations yet.</p>
      )}
      {registrations.data && registrations.data.length > 0 && (
        <ol className="mt-2 space-y-2 text-sm">
          {registrations.data.map((registration) => (
            <li key={registration.id} className="rounded border border-slate-100 p-2">
              <p className="font-medium">{registration.full_name}</p>
              <p className="text-slate-600">
                Submitted{' '}
                <time dateTime={registration.submitted_at}>
                  {new Date(registration.submitted_at).toLocaleString()}
                </time>
                {' · '}Status: {registration.status}
              </p>
              <p className="text-slate-600">
                Age: {registration.age} · Phone: {registration.phone_number}
              </p>
              {registration.dietary_accessibility_notes && (
                <p className="text-slate-600">Notes: {registration.dietary_accessibility_notes}</p>
              )}
              {canDecide && canMakeDecision(registration.status) && (
                <div className="mt-2 space-y-2">
                  <label className="block text-slate-600" htmlFor={`decision-note-${registration.id}`}>
                    Decision note (optional)
                  </label>
                  <input
                    id={`decision-note-${registration.id}`}
                    value={notes[registration.id] ?? ''}
                    onChange={(event) => setNotes({ ...notes, [registration.id]: event.target.value })}
                    className="w-full rounded border border-slate-300 px-2 py-1"
                  />
                  {registration.status !== 'accepted' && (
                    <button
                      type="button"
                      onClick={() => decision.mutate({ id: registration.id, expectedStatus: registration.status, status: 'accepted' })}
                      disabled={decision.isPending}
                      className="rounded bg-slate-900 px-2 py-1 text-white disabled:opacity-50"
                    >
                      Accept
                    </button>
                  )}
                  {registration.status !== 'waitlisted' && (
                    <button
                      type="button"
                      onClick={() => decision.mutate({ id: registration.id, expectedStatus: registration.status, status: 'waitlisted' })}
                      disabled={decision.isPending}
                      className="ml-2 rounded border border-slate-300 px-2 py-1 disabled:opacity-50"
                    >
                      Waitlist
                    </button>
                  )}
                  {decision.isError && <p role="alert" className="text-red-600">{decision.error.message}</p>}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function canMakeDecision(status: RegistrationStatus): boolean {
  return status === 'pending' || status === 'waitlisted' || status === 'accepted'
}

import { useQuery } from '@tanstack/react-query'

import { listEventRegistrations } from '../api/eventRegistrations'
import { useAuth } from '../auth/useAuth'

/** SCRUM-114: a read-only, server-authorised view in the event-management cards. */
export default function RegistrationReviewList({ eventId }: { eventId: string }) {
  const { token } = useAuth()
  const registrations = useQuery({
    queryKey: ['event-requests', eventId, 'registrations', token],
    queryFn: () => listEventRegistrations(token ?? '', eventId),
    enabled: token !== null,
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
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

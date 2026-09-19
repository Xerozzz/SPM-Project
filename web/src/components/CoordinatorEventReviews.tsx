import { useQuery } from '@tanstack/react-query'

import { listReviewableEventRequests } from '../api/eventClarifications'
import { useAuth } from '../auth/useAuth'
import ClarificationThread from './ClarificationThread'

export default function CoordinatorEventReviews() {
  const { token } = useAuth()
  const requests = useQuery({
    queryKey: ['event-requests', 'reviewable', token],
    queryFn: () => listReviewableEventRequests(token ?? ''),
    enabled: token !== null,
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Event requests for review</h2>
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {requests.error.message}
        </p>
      )}
      {requests.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No submitted requests need review.</p>
      )}
      {requests.data && requests.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200">
          {requests.data.map((request) => (
            <li key={request.id} className="py-3">
              <p className="font-medium">{request.name ?? 'Untitled request'}</p>
              <p className="text-sm text-slate-500">Submitted</p>
              <ClarificationThread eventRequestId={request.id} mode="coordinator" />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

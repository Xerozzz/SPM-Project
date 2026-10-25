import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { readCancellation, requestCancellation } from '../api/eventCancellation'
import type { EventRequest } from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-115 AC1: the owning Organiser asks their Coordinator to cancel the event.
 *
 * Closed until opened, so nothing is fetched for an event nobody is cancelling. Earlier
 * requests are listed with their outcome, so a declined request shows why.
 */
export default function RequestCancellation({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const key = ['event-cancellation', event.id, token]
  const record = useQuery({
    queryKey: key,
    queryFn: () => readCancellation(token ?? '', event.id),
    enabled: open && token !== null,
  })
  const ask = useMutation({
    mutationFn: () => requestCancellation(token ?? '', event.id, reason),
    onSuccess: () => {
      setReason('')
      void client.invalidateQueries({ queryKey: key })
    },
  })
  const waiting = record.data?.requests.some((row) => row.status === 'pending') ?? false

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded border border-slate-300 px-3 py-1.5 text-sm"
      >
        Ask to cancel
      </button>
    )
  }

  return (
    <section className="mt-2 rounded border border-slate-200 p-3 text-sm">
      <h3 className="font-medium">Ask to cancel this event</h3>
      {record.isPending && <p className="mt-2">Loading…</p>}
      {record.isError && (
        <p role="alert" className="mt-2 text-red-600">
          {record.error.message}
        </p>
      )}
      {record.data && record.data.requests.length > 0 && (
        <ul className="mt-2 space-y-1">
          {record.data.requests.map((row) => (
            <li key={row.id}>
              {formatSingaporeTime(row.requested_at)}: <q>{row.reason}</q>{' '}
              <span className="font-medium">{outcome(row.status)}</span>
              {row.decision_note && <span> Coordinator: {row.decision_note}</span>}
            </li>
          ))}
        </ul>
      )}
      {waiting ? (
        <p className="mt-2 text-slate-500">Your Coordinator has not answered yet.</p>
      ) : (
        <>
          <label className="mt-2 block">
            Why should it be cancelled?
            <textarea
              value={reason}
              onChange={(change) => setReason(change.target.value)}
              rows={2}
              className="mt-1 block w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            disabled={ask.isPending}
            onClick={() => ask.mutate()}
            className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50"
          >
            Send request
          </button>
        </>
      )}
      {ask.isError && (
        <p role="alert" className="mt-2 text-red-600">
          {ask.error.message}
        </p>
      )}
    </section>
  )
}

function outcome(status: 'pending' | 'applied' | 'declined'): string {
  if (status === 'pending') return 'Waiting.'
  if (status === 'applied') return 'Applied.'
  return 'Declined.'
}

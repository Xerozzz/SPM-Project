import { useQuery } from '@tanstack/react-query'

import { type ChangeItem, listChangeRequests } from '../api/eventChangeRequests'
import { useAuth } from '../auth/useAuth'
import { CHANGE_FIELDS } from '../validation/eventChange'
import ChangeDecision from './ChangeDecision'

/**
 * SCRUM-37 AC3 and AC6: an event's change requests, each changed value shown next to the
 * value it would replace. The Organiser sees their own, the assigned Coordinator sees the
 * event's. The API decides who may read, so this only shows what it returns.
 *
 * SCRUM-47: with `canDecide`, a pending request also offers Approve and Reject. A decided
 * request shows the decision note and what the approval did with each item.
 */
export default function ChangeRequestList({
  eventId,
  canDecide = false,
}: {
  eventId: string
  /** The assigned Coordinator's view. The API still checks who may decide. */
  canDecide?: boolean
}) {
  const { token } = useAuth()
  const requests = useQuery({
    queryKey: ['change-requests', eventId, token],
    queryFn: () => listChangeRequests(token ?? '', eventId),
    enabled: token !== null,
  })

  if (requests.isError) {
    return (
      <p role="alert" className="mt-2 text-sm text-red-600">
        {requests.error.message}
      </p>
    )
  }
  if (!requests.data || requests.data.length === 0) return null

  return (
    <section className="mt-3" aria-label="Change requests">
      <h4 className="text-sm font-medium">Change requests</h4>
      {requests.data.map((request) => (
        <article key={request.id} className="mt-2 rounded bg-slate-50 p-2 text-sm">
          <p>
            <span className="font-medium">Status:</span> <span>{statusLabel(request.status)}</span>
            {' · '}
            {new Date(request.created_at).toLocaleString()}
          </p>
          <p>
            <span className="font-medium">Reason:</span> <span>{request.reason}</span>
          </p>
          {request.decision_note && (
            <p>
              <span className="font-medium">Decision note:</span>{' '}
              <span>{request.decision_note}</span>
            </p>
          )}
          <table className="mt-1 w-full text-left">
            <thead>
              <tr>
                <th className="font-medium">Change</th>
                <th className="font-medium">Current</th>
                <th className="font-medium">Proposed</th>
                {request.status === 'approved' && <th className="font-medium">Result</th>}
              </tr>
            </thead>
            <tbody>
              {request.items.map((item, index) => (
                <tr key={index}>
                  <td>{itemLabel(item)}</td>
                  <td>{shown(item.current_value)}</td>
                  <td>{shown(item.proposed_value)}</td>
                  {request.status === 'approved' && <td>{outcomeLabel(item.outcome)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          {canDecide && request.status === 'pending' && (
            <ChangeDecision eventId={eventId} changeId={request.id} />
          )}
        </article>
      ))}
    </section>
  )
}

function statusLabel(status: string): string {
  if (status === 'pending') return 'Pending review'
  if (status === 'approved') return 'Approved'
  if (status === 'rejected') return 'Rejected'
  return status
}

/** SCRUM-47 AC3/AC4: event fields are applied, arrangements go through their own flows. */
function outcomeLabel(outcome: string | null): string {
  if (outcome === 'applied') return 'Applied'
  if (outcome === 'needs_replanning') return 'Needs replanning'
  return '-'
}

const EVENT_LABELS: Record<string, string> = Object.fromEntries(CHANGE_FIELDS)

const VALUE_LABELS: Record<string, string> = {
  session_label: 'name',
  start_at: 'start',
  end_at: 'end',
  quantity: 'quantity',
  technical_requirements: 'technical needs',
  add: 'add',
  remove: 'remove',
}

function itemLabel(item: ChangeItem): string {
  if (item.target === 'event') return EVENT_LABELS[item.field] ?? item.field
  const what = item.target === 'session' ? 'Session' : 'Equipment'
  return `${what} ${VALUE_LABELS[item.field] ?? item.field}`
}

/** Dates in local time, equipment lines as "type x quantity", nothing as a dash. */
function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') {
    const line = value as { equipment_type?: string; quantity?: number }
    return `${line.equipment_type ?? ''} x ${line.quantity ?? ''}`
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return new Date(value).toLocaleString()
  }
  return String(value)
}

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ChangeRejectedError, type Decision, decideChangeRequest } from '../api/eventChangeRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-47 AC1: the assigned Coordinator approves or rejects a pending change request
 * with a note. The API checks who may decide, whether the request is stale (AC2) and
 * whether it was already decided (AC9), so this only sends the decision and shows the
 * outcome.
 */
export default function ChangeDecision({
  eventId,
  changeId,
}: {
  eventId: string
  changeId: string
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [note, setNote] = useState('')

  const decide = useMutation({
    mutationFn: (decision: Decision) =>
      decideChangeRequest(token ?? '', eventId, changeId, decision, note),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['change-requests', eventId] })
      // An approval changes the event itself, and may return it to planning.
      void client.invalidateQueries({ queryKey: ['event-requests'] })
    },
  })
  const problems = decide.error instanceof ChangeRejectedError ? decide.error.problems : []

  return (
    <div className="mt-2 space-y-2">
      <label className="block font-medium">
        Decision note
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="mt-1 block w-full rounded border border-slate-300 p-2 font-normal"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => decide.mutate('approve')}
          disabled={decide.isPending || !note.trim()}
          className="rounded bg-green-700 px-3 py-1.5 text-white disabled:opacity-50"
        >
          Approve change
        </button>
        <button
          type="button"
          onClick={() => decide.mutate('reject')}
          disabled={decide.isPending || !note.trim()}
          className="rounded bg-red-700 px-3 py-1.5 text-white disabled:opacity-50"
        >
          Reject change
        </button>
      </div>
      {decide.isError && (
        <div role="alert" className="rounded bg-amber-50 p-2 text-amber-900">
          <p>{decide.error.message}</p>
          {problems.length > 0 && (
            <ul className="list-disc pl-5">
              {problems.map((problem) => (
                <li key={`${problem.field} ${problem.reason}`}>
                  {problem.field} {problem.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

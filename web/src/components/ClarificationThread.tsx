import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { listClarifications, requestClarification } from '../api/eventClarifications'
import { useAuth } from '../auth/useAuth'

interface Props {
  eventRequestId: string
  canRequest: boolean
}

/**
 * SCRUM-106: internal notes for the assigned Coordinator only. The Organiser has no
 * in-app clarification surface — this component is never rendered for them — and the
 * API refuses non-assignees, so hiding here is supplementary, not the boundary.
 */
export default function ClarificationThread({ eventRequestId, canRequest }: Props) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const queryKey = ['event-clarifications', eventRequestId, token]
  const history = useQuery({
    queryKey,
    queryFn: () => listClarifications(token ?? '', eventRequestId),
    enabled: token !== null,
  })
  const send = useMutation({
    mutationFn: (text: string) => requestClarification(token ?? '', eventRequestId, text),
    onSuccess: () => {
      setMessage('')
      void queryClient.invalidateQueries({ queryKey })
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = message.trim()
    if (text) send.mutate(text)
  }

  return (
    <section className="mt-3 border-t border-slate-200 pt-3" aria-label="Clarification history">
      <h3 className="text-sm font-medium">Internal clarification notes</h3>
      {history.isPending && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
      {history.isError && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {history.error.message}
        </p>
      )}
      {history.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No internal notes yet.</p>
      )}
      {history.data && history.data.length > 0 && (
        <ol className="mt-2 space-y-2">
          {history.data.map((entry) => (
            <li
              key={entry.id}
              className={
                entry.kind === 'request'
                  ? 'border-l-2 border-amber-400 pl-3 text-sm'
                  : 'border-l-2 border-slate-300 pl-3 text-sm'
              }
            >
              <p className="text-xs font-medium text-slate-600">Coordinator note</p>
              <p>{entry.message}</p>
              <time className="text-xs text-slate-500" dateTime={entry.created_at}>
                {new Date(entry.created_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
      )}
      {canRequest && (
        <form className="mt-3" onSubmit={submit}>
          <label className="text-sm font-medium" htmlFor={`clarification-${eventRequestId}`}>
            Internal note
          </label>
          <textarea
            id={`clarification-${eventRequestId}`}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={3}
            className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
          />
          <button
            type="submit"
            disabled={!message.trim() || send.isPending}
            className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Record internal note
          </button>
          {send.isSuccess && (
            <p className="mt-2 text-sm text-green-700" role="status">
              Message sent.
            </p>
          )}
          {send.isError && (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {send.error.message}
            </p>
          )}
        </form>
      )}
    </section>
  )
}

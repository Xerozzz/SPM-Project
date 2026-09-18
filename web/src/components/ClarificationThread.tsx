import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  listClarifications,
  requestClarification,
  respondToClarification,
} from '../api/eventClarifications'
import { useAuth } from '../auth/useAuth'

interface Props {
  eventRequestId: string
  mode: 'coordinator' | 'organiser'
}

export default function ClarificationThread({ eventRequestId, mode }: Props) {
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
    mutationFn: (text: string) =>
      mode === 'coordinator'
        ? requestClarification(token ?? '', eventRequestId, text)
        : respondToClarification(token ?? '', eventRequestId, text),
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

  const action = mode === 'coordinator' ? 'Request clarification' : 'Send response'

  return (
    <section className="mt-3 border-t border-slate-200 pt-3" aria-label="Clarification history">
      <h3 className="text-sm font-medium">Clarification history</h3>
      {history.isPending && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
      {history.isError && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {history.error.message}
        </p>
      )}
      {history.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No clarification messages yet.</p>
      )}
      {history.data && history.data.length > 0 && (
        <ol className="mt-2 space-y-2">
          {history.data.map((entry) => (
            <li key={entry.id} className="border-l-2 border-slate-300 pl-3 text-sm">
              <p>{entry.message}</p>
              <time className="text-xs text-slate-500" dateTime={entry.created_at}>
                {new Date(entry.created_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
      )}
      <form className="mt-3" onSubmit={submit}>
        <label className="text-sm font-medium" htmlFor={`clarification-${eventRequestId}-${mode}`}>
          {mode === 'coordinator' ? 'Clarification request' : 'Response'}
        </label>
        <textarea
          id={`clarification-${eventRequestId}-${mode}`}
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
          {action}
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
    </section>
  )
}

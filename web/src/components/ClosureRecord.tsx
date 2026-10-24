import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { attendanceOf, correctClosure, readClosure, type ClosureNote } from '../api/eventCompletion'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-86 AC4, AC5: a completed event's closure record and every earlier version.
 *
 * A correction adds a version. Earlier versions stay listed with who recorded them and
 * when, so nothing is silently overwritten.
 */
export default function ClosureRecord({
  eventId,
  canCorrect = false,
}: {
  eventId: string
  canCorrect?: boolean
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const key = ['event-closure', eventId, token]
  const closure = useQuery({
    queryKey: key,
    queryFn: () => readClosure(token ?? '', eventId),
    enabled: token !== null,
  })
  const [attendance, setAttendance] = useState('')
  const [notes, setNotes] = useState('')
  const correct = useMutation({
    mutationFn: () =>
      correctClosure(token ?? '', eventId, {
        actual_attendance: attendanceOf(attendance),
        notes: notes.trim() === '' ? null : notes,
      }),
    onSuccess: () => {
      setAttendance('')
      setNotes('')
      void client.invalidateQueries({ queryKey: key })
    },
  })

  if (closure.isPending) return <p className="mt-2 text-sm">Loading closure record…</p>
  if (closure.isError) {
    return (
      <p role="alert" className="mt-2 text-sm text-red-600">
        {closure.error.message}
      </p>
    )
  }
  const { current, history, completed_at } = closure.data

  return (
    <section className="mt-3 rounded border border-slate-200 p-3 text-sm">
      <h3 className="font-medium">Closure record</h3>
      {completed_at && (
        <p className="text-slate-500">Completed {formatSingaporeTime(completed_at)}.</p>
      )}
      {current && <NoteView note={current} />}
      {history.length > 1 && (
        <details className="mt-2">
          <summary>Earlier versions ({history.length - 1})</summary>
          <ul className="mt-1 space-y-1">
            {history.slice(0, -1).map((note) => (
              <li key={note.version}>
                <NoteView note={note} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {canCorrect && (
        <div className="mt-3">
          <h4 className="font-medium">Correct the record</h4>
          <label className="mt-1 block">
            Actual attendance
            <input
              type="number"
              min={0}
              step={1}
              value={attendance}
              onChange={(change) => setAttendance(change.target.value)}
              className="mt-1 block w-32 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <label className="mt-1 block">
            Notes
            <textarea
              value={notes}
              onChange={(change) => setNotes(change.target.value)}
              rows={2}
              className="mt-1 block w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            disabled={correct.isPending}
            onClick={() => correct.mutate()}
            className="mt-2 rounded border border-slate-300 px-3 py-1"
          >
            Save correction
          </button>
          {correct.isError && (
            <p role="alert" className="mt-1 text-red-600">
              {correct.error.message}
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function NoteView({ note }: { note: ClosureNote }) {
  return (
    <div className="mt-1">
      <p>
        Version {note.version}, recorded {formatSingaporeTime(note.recorded_at)}.
      </p>
      <p>
        Actual attendance:{' '}
        {note.actual_attendance === null ? 'not recorded' : note.actual_attendance}
      </p>
      <p>Notes: {note.notes ?? 'none'}</p>
    </div>
  )
}

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { attendanceOf, completeEvent } from '../api/eventCompletion'
import type { EventRequest } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-86: the assigned Coordinator completes a Confirmed event once it has ended.
 *
 * The API decides whether it has ended. A refusal is shown as it comes back, so the
 * Coordinator reads "This event has not ended yet" rather than a disabled button.
 */
export default function CompleteEvent({
  event,
  onCompleted,
}: {
  event: EventRequest
  /** Told to the parent, because a completed event moves to the completed list. */
  onCompleted: (message: string) => void
}) {
  const { token } = useAuth()
  const [attendance, setAttendance] = useState('')
  const [notes, setNotes] = useState('')
  const complete = useMutation({
    mutationFn: () =>
      completeEvent(token ?? '', event.id, {
        actual_attendance: attendanceOf(attendance),
        notes: notes.trim() === '' ? null : notes,
      }),
    onSuccess: () => onCompleted(`“${event.name}” is completed. Its closure record is saved.`),
  })

  return (
    <section className="mt-4 rounded border border-slate-200 p-3 text-sm">
      <h3 className="font-medium">Complete this event</h3>
      <p className="mt-1 text-slate-500">
        Once the event has ended, record how it went. Completing closes registration and cannot be
        undone. Bookings, equipment and registrations are kept.
      </p>
      <label className="mt-2 block">
        Actual attendance (optional)
        <input
          type="number"
          min={0}
          step={1}
          value={attendance}
          onChange={(change) => setAttendance(change.target.value)}
          className="mt-1 block w-32 rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <label className="mt-2 block">
        Operational notes and issues (optional)
        <textarea
          value={notes}
          onChange={(change) => setNotes(change.target.value)}
          rows={3}
          className="mt-1 block w-full rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <button
        type="button"
        disabled={complete.isPending}
        aria-label={`Complete ${event.name}`}
        onClick={() => complete.mutate()}
        className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50"
      >
        Mark event completed
      </button>
      {complete.isError && (
        <p role="alert" className="mt-2 text-red-600">
          {complete.error.message}
        </p>
      )}
    </section>
  )
}

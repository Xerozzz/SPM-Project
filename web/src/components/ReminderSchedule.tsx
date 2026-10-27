import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  COMMON_LEAD_TIMES,
  describeLeadTime,
  InvalidScheduleError,
  readReminders,
  type Reminder,
  writeReminders,
} from '../api/eventReminders'
import type { EventRequest } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-85: the Coordinator's own reminders about work still outstanding.
 *
 * Theirs alone — the API refuses anyone else, including a Lead and the owning Organiser
 * — so this sits on their card rather than anywhere the event is on show.
 *
 * Every rule stays on the API. What a valid lead time is, and what counts as outstanding
 * when an occurrence falls due, are its answers; this shows the schedule and sends the
 * change. A reminder already sent is shown as sent rather than hidden, because the
 * absence of a pending one is otherwise indistinguishable from never having set it.
 */
export default function ReminderSchedule({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [custom, setCustom] = useState('')
  const [failure, setFailure] = useState<{ text: string; reasons: string[] } | null>(null)

  const queryKey = ['event-reminders', event.id, token]
  const schedule = useQuery({
    queryKey,
    queryFn: () => readReminders(token ?? '', event.id),
    enabled: token !== null,
  })

  const save = useMutation({
    mutationFn: (leadMinutes: number[]) => writeReminders(token ?? '', event.id, leadMinutes),
    onError: (error: Error) => {
      setFailure({
        text: error.message,
        reasons:
          error instanceof InvalidScheduleError
            ? error.problems.map((problem) => problem.reason)
            : [],
      })
    },
    onSuccess: () => {
      setFailure(null)
      setCustom('')
      void client.invalidateQueries({ queryKey })
    },
  })

  const current: Reminder[] = schedule.data ?? []
  const minutes = current.map((row) => row.lead_minutes)
  // Nothing may be sent before the existing schedule is known. The API replaces the
  // whole schedule, so a click landing while it was still loading would send a list
  // built from no reminders and wipe the ones already there.
  const busy = save.isPending || !schedule.isSuccess

  function change(next: number[]) {
    setFailure(null)
    save.mutate(next)
  }

  return (
    <section className="mt-4 rounded border border-slate-200 p-3">
      <h3 className="text-sm font-medium">Reminders</h3>
      <p className="mt-1 text-sm text-slate-500">
        Tell me before this event starts if anything is still outstanding. Only you see these, and
        nothing is sent once the event has started.
      </p>

      {schedule.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {schedule.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {schedule.error.message}
        </p>
      )}

      {schedule.isSuccess && current.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No reminders set.</p>
      )}

      {current.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {current.map((reminder) => (
            <li key={reminder.id} className="flex items-center gap-2">
              <span>{describeLeadTime(reminder.lead_minutes)}</span>
              {reminder.processed_at !== null && (
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                  Already sent
                </span>
              )}
              <button
                type="button"
                disabled={busy}
                aria-label={`Remove the ${describeLeadTime(reminder.lead_minutes)} reminder for ${event.name}`}
                onClick={() => change(minutes.filter((value) => value !== reminder.lead_minutes))}
                className="text-xs underline disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {COMMON_LEAD_TIMES.filter((option) => !minutes.includes(option.minutes)).map((option) => (
          <button
            key={option.minutes}
            type="button"
            disabled={busy}
            onClick={() => change([...minutes, option.minutes])}
            className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
          >
            Add {option.label}
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          <span className="block">Minutes before</span>
          <input
            type="number"
            min={1}
            step={1}
            value={custom}
            aria-label={`Minutes before ${event.name} to remind me`}
            onChange={(changed) => setCustom(changed.target.value)}
            className="mt-1 w-32 rounded border border-slate-300 p-1.5 text-sm"
          />
        </label>
        <button
          type="button"
          disabled={busy || custom.trim() === ''}
          onClick={() => change([...minutes, Number(custom)])}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Add reminder
        </button>
      </div>

      {failure && (
        <div role="alert" className="mt-2 text-sm text-red-600">
          <p>{failure.text}</p>
          {failure.reasons.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {failure.reasons.map((reason) => (
                <li key={reason}>A reminder {reason}.</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

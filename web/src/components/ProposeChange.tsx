import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  ChangeRejectedError,
  type ChangePlan,
  getChangePlan,
  proposeChange,
} from '../api/eventChangeRequests'
import { useAuth } from '../auth/useAuth'
import {
  CHANGE_FIELDS,
  type ChangeDraft,
  changeRequestOf,
  draftOf,
} from '../validation/eventChange'

/**
 * SCRUM-37: the owning Organiser proposes significant changes after submission. The form
 * starts from today's values and sends only what changed, with a reason. Nothing on the
 * event changes until the Coordinator decides (AC5), and the API checks every value (AC4).
 */
export default function ProposeChange({
  eventId,
  onClose,
}: {
  eventId: string
  onClose: () => void
}) {
  const { token } = useAuth()
  const plan = useQuery({
    queryKey: ['change-plan', eventId, token],
    queryFn: () => getChangePlan(token ?? '', eventId),
    enabled: token !== null,
  })

  if (plan.isPending) return <p className="mt-2 text-sm">Loading the current plan...</p>
  if (plan.isError) {
    return (
      <p role="alert" className="mt-2 text-sm text-red-600">
        {plan.error.message}
      </p>
    )
  }
  return <ChangeForm eventId={eventId} plan={plan.data} onClose={onClose} />
}

function ChangeForm({
  eventId,
  plan,
  onClose,
}: {
  eventId: string
  plan: ChangePlan
  onClose: () => void
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [draft, setDraft] = useState<ChangeDraft>(() => draftOf(plan))
  // One key per submit action (AC8). A retry after a lost response reuses it, so the API
  // returns the first request instead of recording a second one.
  const [submissionKey, setSubmissionKey] = useState(() => crypto.randomUUID())
  const [sent, setSent] = useState(false)

  const send = useMutation({
    mutationFn: () =>
      proposeChange(token ?? '', eventId, changeRequestOf(plan, draft, submissionKey)),
    onSuccess: () => {
      setSent(true)
      setSubmissionKey(crypto.randomUUID())
      setDraft(draftOf(plan))
      void client.invalidateQueries({ queryKey: ['change-requests', eventId] })
    },
  })
  const problems = send.error instanceof ChangeRejectedError ? send.error.problems : []

  const setEvent = (field: string, value: string) =>
    setDraft({ ...draft, event: { ...draft.event, [field]: value } })

  return (
    <form
      className="mt-3 space-y-3 rounded border border-slate-200 p-3 text-sm"
      aria-label="Propose a change"
      onSubmit={(event) => {
        event.preventDefault()
        setSent(false)
        send.mutate()
      }}
    >
      <p className="text-slate-600">
        Change only what you need. Your event stays as it is until the coordinator reviews the
        request.
      </p>

      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="font-medium">Event</legend>
        {CHANGE_FIELDS.map(([field, label]) => (
          <label key={field} className="block">
            {label}
            {field === 'venue_requirement' ? (
              <select
                value={draft.event[field]}
                onChange={(e) => setEvent(field, e.target.value)}
                className="mt-1 block w-full rounded border border-slate-300 p-1"
              >
                {[...new Set([draft.event[field], ...plan.venue_options])].map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={
                  field.endsWith('_at')
                    ? 'datetime-local'
                    : field === 'expected_attendance'
                      ? 'number'
                      : 'text'
                }
                value={draft.event[field]}
                onChange={(e) => setEvent(field, e.target.value)}
                className="mt-1 block w-full rounded border border-slate-300 p-1"
              />
            )}
          </label>
        ))}
      </fieldset>

      {draft.sessions.length > 0 && (
        <fieldset>
          <legend className="font-medium">Sessions</legend>
          {draft.sessions.map((session, index) => (
            <div key={session.id} className="mt-1 grid gap-2 sm:grid-cols-3">
              {(
                [
                  ['label', 'Session name', 'text'],
                  ['start', 'Session start', 'datetime-local'],
                  ['end', 'Session end', 'datetime-local'],
                ] as const
              ).map(([key, label, type]) => (
                <label key={key} className="block">
                  {label} ({plan.sessions[index].session_label})
                  <input
                    type={type}
                    value={session[key]}
                    onChange={(e) => {
                      const sessions = [...draft.sessions]
                      sessions[index] = { ...session, [key]: e.target.value }
                      setDraft({ ...draft, sessions })
                    }}
                    className="mt-1 block w-full rounded border border-slate-300 p-1"
                  />
                </label>
              ))}
            </div>
          ))}
        </fieldset>
      )}

      <fieldset>
        <legend className="font-medium">Equipment</legend>
        {draft.equipment.map((line, index) => {
          const type = plan.equipment[index].equipment_type
          const update = (change: Partial<typeof line>) => {
            const equipment = [...draft.equipment]
            equipment[index] = { ...line, ...change }
            setDraft({ ...draft, equipment })
          }
          return (
            <div key={line.id} className="mt-1 flex flex-wrap items-end gap-2">
              <label>
                {type} quantity
                <input
                  type="number"
                  value={line.quantity}
                  disabled={line.remove}
                  onChange={(e) => update({ quantity: e.target.value })}
                  className="ml-1 w-20 rounded border border-slate-300 p-1"
                />
              </label>
              <label>
                {type} technical needs
                <input
                  value={line.technical}
                  disabled={line.remove}
                  onChange={(e) => update({ technical: e.target.value })}
                  className="ml-1 rounded border border-slate-300 p-1"
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={line.remove}
                  onChange={(e) => update({ remove: e.target.checked })}
                />{' '}
                Remove {type}
              </label>
            </div>
          )
        })}
        {draft.added.map((line, index) => (
          <div key={index} className="mt-1 flex flex-wrap items-end gap-2">
            <label>
              New equipment type
              <select
                value={line.type}
                onChange={(e) => {
                  const added = [...draft.added]
                  added[index] = { ...line, type: e.target.value }
                  setDraft({ ...draft, added })
                }}
                className="ml-1 rounded border border-slate-300 p-1"
              >
                {plan.equipment_types.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              New equipment quantity
              <input
                type="number"
                value={line.quantity}
                onChange={(e) => {
                  const added = [...draft.added]
                  added[index] = { ...line, quantity: e.target.value }
                  setDraft({ ...draft, added })
                }}
                className="ml-1 w-20 rounded border border-slate-300 p-1"
              />
            </label>
          </div>
        ))}
        {plan.equipment_types.length > 0 && (
          <button
            type="button"
            onClick={() =>
              setDraft({
                ...draft,
                added: [...draft.added, { type: plan.equipment_types[0], quantity: '1' }],
              })
            }
            className="mt-2 rounded border border-slate-300 px-2 py-1"
          >
            Add equipment
          </button>
        )}
      </fieldset>

      <label className="block font-medium">
        Reason for the change
        <textarea
          value={draft.reason}
          onChange={(e) => setDraft({ ...draft, reason: e.target.value })}
          className="mt-1 block w-full rounded border border-slate-300 p-2 font-normal"
        />
      </label>

      {problems.length > 0 && (
        <div role="alert" className="rounded bg-amber-50 p-2 text-amber-900">
          <p>The change request was not sent. Please correct:</p>
          <ul className="list-disc pl-5">
            {problems.map((problem) => (
              <li key={`${problem.field} ${problem.reason}`}>
                {problem.field} {problem.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {send.isError && problems.length === 0 && (
        <p role="alert" className="text-red-600">
          {send.error.message}. You can try again safely.
        </p>
      )}
      {sent && (
        <p role="status" className="rounded bg-green-50 p-2 text-green-800">
          Change request sent. The coordinator will review it, and your event stays as it is until
          then.
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={send.isPending}
          className="rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50"
        >
          Send change request
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-300 px-3 py-1.5"
        >
          Close
        </button>
      </div>
    </form>
  )
}

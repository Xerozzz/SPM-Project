import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  type EventRequest,
  EventRequestValidationError,
  updatePlanningInfo,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import {
  blankPlanningFields,
  changedPlanningInfo,
  ORDINARY_FIELDS,
  planningInfoOf,
  type PlanningInfo,
} from '../validation/planningInfo'

/**
 * SCRUM-36: the assigned coordinator edits ordinary planning information. Only the fields
 * in ORDINARY_FIELDS are offered (AC3), and the API decides who may save (AC4).
 */
export default function PlanningInfoEditor({ request }: { request: EventRequest }) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<PlanningInfo>(() => planningInfoOf(request))
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: () =>
      updatePlanningInfo(token ?? '', request.id, changedPlanningInfo(request, draft)),
    onSuccess: () => {
      setEditing(false)
      setSaved(true)
      void client.invalidateQueries({ queryKey: ['event-requests'] })
    },
  })

  if (!editing) {
    return (
      <div className="mt-3">
        <button
          type="button"
          onClick={() => {
            setDraft(planningInfoOf(request))
            setSaved(false)
            save.reset()
            setEditing(true)
          }}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Edit planning information
        </button>
        {saved && (
          <p role="status" className="mt-2 text-sm text-green-800">
            Planning information saved.
          </p>
        )}
      </div>
    )
  }

  const blank = blankPlanningFields(draft)
  const unchanged = Object.keys(changedPlanningInfo(request, draft)).length === 0
  return (
    <form
      aria-label="Edit planning information"
      className="mt-3 rounded border border-slate-200 p-3"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <p className="text-sm text-slate-600">
        Date, time, attendance, venue, equipment, layout and accessibility cannot be changed here.
        The Organiser proposes those as a change request.
      </p>
      {ORDINARY_FIELDS.map(([field, label]) => (
        <div key={field} className="mt-2">
          <label className="block text-sm font-medium" htmlFor={`${field}-${request.id}`}>
            {label}
          </label>
          <input
            id={`${field}-${request.id}`}
            value={draft[field]}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
            className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
          />
          {blank.includes(field) && (
            <p className="mt-1 text-sm text-red-600">{label} is required.</p>
          )}
        </div>
      ))}
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {save.error instanceof EventRequestValidationError
            ? save.error.problems.map((p) => `${p.field} ${p.reason}`).join(', ')
            : `Could not save: ${save.error.message}`}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="submit"
          disabled={save.isPending || blank.length > 0 || unchanged}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

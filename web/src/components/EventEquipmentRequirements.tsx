import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  addEquipmentRequirement,
  type EquipmentRequirement,
  listCatalogueTypes,
  listEquipmentRequirements,
  REQUIREMENT_FIELD_LABELS,
  removeEquipmentRequirement,
  type RequirementProblem,
  RequirementRejectedError,
  REVIEW_LABELS,
  updateEquipmentRequirement,
} from '../api/equipmentRequirements'
import type { EventRequest } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-43: the assigned Coordinator maintains what an event needs.
 *
 * The rules are the API's: which types are allowed (AC3), that one type is one line
 * (AC4), that a change sends the line back for review (AC5) and that a removal keeps its
 * history (AC7). This component sends the action and shows the answer, including the
 * fields a refusal names, so the Coordinator can correct them without guessing.
 *
 * Only rendered for the assigned Coordinator of an event being planned, which is the
 * same rule `EventAccess.MAINTAIN_EQUIPMENT` applies on the API (AC2, AC10). The API is
 * what actually refuses anyone else; hiding it here is for the person, not for safety.
 */
/**
 * AC6: what a change did to anything already reserved against the requirement.
 *
 * Nothing is released. Saying only "removed" would let a Coordinator believe the matter
 * is closed while Technical Support still hold equipment for a line that no longer says
 * what it did.
 */
function reservationNote(requirement: EquipmentRequirement): string {
  if (!requirement.has_flagged_reservation) return ''
  return ' Technical Support have equipment reserved for it and will reconsider.'
}

export default function EventEquipmentRequirements({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const emptyValues = { equipment_type: '', quantity: '', technical: '' }
  const [values, setValues] = useState(emptyValues)
  const [problems, setProblems] = useState<RequirementProblem[]>([])
  const [failure, setFailure] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  const queryKey = ['equipment-requirements', event.id, token]
  const requirements = useQuery({
    queryKey,
    queryFn: () => listEquipmentRequirements(token ?? '', event.id),
    enabled: token !== null,
  })
  const types = useQuery({
    queryKey: ['equipment-catalogue-types', event.id, token],
    queryFn: () => listCatalogueTypes(token ?? '', event.id),
    enabled: token !== null,
  })

  function refresh() {
    void queryClient.invalidateQueries({ queryKey })
  }

  /** Every save reports the same way, so no action can fail silently. */
  function failed(error: Error) {
    if (error instanceof RequirementRejectedError) {
      setProblems(error.problems)
      setFailure(null)
    } else {
      setProblems([])
      setFailure(error.message)
    }
  }

  function starting() {
    setProblems([])
    setFailure(null)
    setOutcome(null)
  }

  const add = useMutation({
    mutationFn: (input: typeof emptyValues) =>
      addEquipmentRequirement(token ?? '', event.id, {
        // Blanks go as absent rather than as "" or 0, so the API reports a missing
        // quantity rather than an invalid one, and names the field either way.
        equipment_type: input.equipment_type === '' ? null : input.equipment_type,
        quantity: input.quantity === '' ? null : Number(input.quantity),
        technical_requirements: input.technical.trim() === '' ? null : input.technical,
      }),
    onError: failed,
    onSuccess: (requirement) => {
      setOutcome(`${requirement.equipment_type} added. Technical Support will review it.`)
      setValues(emptyValues)
      refresh()
    },
  })

  const change = useMutation({
    mutationFn: (input: { id: string; quantity: number }) =>
      updateEquipmentRequirement(token ?? '', event.id, input.id, { quantity: input.quantity }),
    onError: failed,
    onSuccess: (requirement) => {
      setOutcome(
        `${requirement.equipment_type} updated. It is back to ${REVIEW_LABELS[
          requirement.review_status
        ].toLowerCase()}.${reservationNote(requirement)}`,
      )
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (requirement: EquipmentRequirement) =>
      removeEquipmentRequirement(token ?? '', event.id, requirement.id),
    onError: failed,
    onSuccess: (requirement) => {
      setOutcome(
        `${requirement.equipment_type} removed. It stays in the event's history.` +
          reservationNote(requirement),
      )
      refresh()
    },
  })

  const busy = add.isPending || change.isPending || remove.isPending

  function submit(submitted: FormEvent<HTMLFormElement>) {
    submitted.preventDefault()
    starting()
    add.mutate(values)
  }

  return (
    <section className="mt-4 rounded border border-slate-200 p-3">
      <h4 className="font-medium">Equipment requirements</h4>
      <p className="mt-1 text-sm text-slate-500">
        What this event needs. Adding or changing a line sends it back to Technical Support
        to assess. Nothing here reserves equipment.
      </p>

      {requirements.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requirements.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {requirements.error.message}
        </p>
      )}
      {requirements.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">Nothing is required for this event yet.</p>
      )}

      {requirements.data && requirements.data.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-200 text-sm">
          {requirements.data.map((requirement) => (
            <li key={requirement.id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="font-medium">{requirement.equipment_type}</span>
              <label className="flex items-center gap-1">
                <span className="sr-only">Quantity for {requirement.equipment_type}</span>
                <input
                  type="number"
                  min={1}
                  defaultValue={requirement.quantity}
                  aria-label={`Quantity for ${requirement.equipment_type}`}
                  onBlur={(blurred) => {
                    const quantity = Number(blurred.target.value)
                    if (quantity === requirement.quantity) return
                    starting()
                    change.mutate({ id: requirement.id, quantity })
                  }}
                  className="w-20 rounded border border-slate-300 p-1"
                />
              </label>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                {REVIEW_LABELS[requirement.review_status]}
              </span>
              {requirement.reserved_quantity > 0 && (
                <span className="text-xs text-slate-500">
                  {requirement.reserved_quantity} of {requirement.quantity} reserved
                </span>
              )}
              {/* AC6: changing or removing a requirement does not release what was
                  reserved against it. Technical Support reconsider it, and the AC says
                  the Coordinator can see the flag, which is this. Without it a
                  Coordinator changes a quantity and never learns a commitment is now in
                  question. */}
              {requirement.has_flagged_reservation && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                  Reservation to reconsider
                </span>
              )}
              {requirement.technical_requirements && (
                <span className="text-slate-500">{requirement.technical_requirements}</span>
              )}
              <button
                type="button"
                disabled={busy}
                aria-label={`Remove ${requirement.equipment_type}`}
                onClick={() => {
                  starting()
                  remove.mutate(requirement)
                }}
                className="ml-auto rounded border border-slate-300 px-2 py-1 disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={submit}>
        <label className="text-sm">
          <span className="block">Equipment type</span>
          <select
            value={values.equipment_type}
            onChange={(changed) =>
              setValues({ ...values, equipment_type: changed.target.value })
            }
            className="mt-1 rounded border border-slate-300 p-1"
          >
            <option value="">Select equipment</option>
            {types.data?.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block">Quantity</span>
          <input
            type="number"
            min={1}
            value={values.quantity}
            onChange={(changed) => setValues({ ...values, quantity: changed.target.value })}
            className="mt-1 w-20 rounded border border-slate-300 p-1"
          />
        </label>
        <label className="text-sm">
          <span className="block">Technical requirements</span>
          <input
            type="text"
            value={values.technical}
            onChange={(changed) => setValues({ ...values, technical: changed.target.value })}
            className="mt-1 rounded border border-slate-300 p-1"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Add requirement
        </button>
      </form>

      {problems.length > 0 && (
        <ul role="alert" className="mt-2 list-disc pl-5 text-sm text-red-600">
          {problems.map((problem) => (
            <li key={problem.field}>
              {REQUIREMENT_FIELD_LABELS[problem.field] ?? problem.field} {problem.reason}
            </li>
          ))}
        </ul>
      )}
      {failure && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {failure}
        </p>
      )}
      {outcome && (
        <p role="status" className="mt-2 text-sm text-green-700">
          {outcome}
        </p>
      )}
    </section>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useState } from 'react'

import {
  createEquipment,
  deactivateEquipment,
  listEquipment,
  OPERATIONAL_STATUSES,
  type EquipmentInput,
  type EquipmentProblem,
  EquipmentRejectedError,
  type Equipment,
  updateEquipment,
} from '../api/equipment'
import { useAuth } from '../auth/useAuth'
import { matchesSearch } from '../presentation/search'

const emptyForm: EquipmentInput = {
  equipment_type: '',
  description: null,
  total_quantity: null,
  location: '',
  operational_status: '',
}

/** SCRUM-84: Technical Support Staff add and view equipment inventory entries. */
export default function EquipmentCatalogue() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const queryKey = ['equipment', token]
  const [values, setValues] = useState<EquipmentInput>(emptyForm)
  const [problems, setProblems] = useState<EquipmentProblem[]>([])
  const [outcome, setOutcome] = useState<string | null>(null)
  const [deactivationOutcome, setDeactivationOutcome] = useState<string | null>(null)
  const [editing, setEditing] = useState<Equipment | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [search, setSearch] = useState('')
  const catalogue = useQuery({
    queryKey,
    queryFn: () => listEquipment(token ?? ''),
    enabled: token !== null,
  })

  const save = useMutation({
    mutationFn: () =>
      editing === null
        ? createEquipment(token ?? '', values)
        : updateEquipment(token ?? '', editing.id, values),
    onSuccess: (equipment) => {
      setValues(emptyForm)
      const wasEditing = editing !== null
      setEditing(null)
      setShowForm(false)
      setProblems([])
      setOutcome(
        wasEditing
          ? `“${equipment.equipment_type}” has been updated in the catalogue.`
          : `“${equipment.equipment_type}” has been added to the catalogue.`,
      )
      void queryClient.invalidateQueries({ queryKey })
    },
    onError: (error: Error) => {
      if (error instanceof EquipmentRejectedError) {
        setProblems(error.problems)
        setOutcome(null)
      } else {
        setProblems([])
        setOutcome(error.message)
      }
    },
  })

  const deactivate = useMutation({
    mutationFn: (equipment: Equipment) => deactivateEquipment(token ?? '', equipment.id),
    onSuccess: (equipment) => {
      setDeactivationOutcome(
        `“${equipment.equipment_type}” has been deactivated and can no longer be selected.`,
      )
      void queryClient.invalidateQueries({ queryKey })
    },
    onError: (error: Error) => setOutcome(error.message),
  })

  function reasonFor(field: string) {
    return problems.find((problem) => problem.field === field)?.reason
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate()
  }

  function startEditing(equipment: Equipment) {
    setEditing(equipment)
    setShowForm(true)
    setValues({
      equipment_type: equipment.equipment_type,
      description: equipment.description,
      total_quantity: equipment.total_quantity,
      location: equipment.location,
      operational_status: equipment.operational_status,
    })
    setProblems([])
    setOutcome(null)
  }

  function cancelEditing() {
    setEditing(null)
    setShowForm(false)
    setValues(emptyForm)
    setProblems([])
  }

  return (
    <section>
      {!showForm && (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="block max-w-md flex-1 text-sm font-medium">
            Search equipment
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Type, location or status"
              className="cs-field"
            />
          </label>
          <button
            type="button"
            className="cs-button"
            onClick={() => {
              setEditing(null)
              setValues(emptyForm)
              setProblems([])
              setOutcome(null)
              setShowForm(true)
            }}
          >
            <span aria-hidden="true" className="mr-1">
              +
            </span>
            Add equipment
          </button>
        </div>
      )}
      {catalogue.isPending && <p className="mt-2 text-sm">Loading equipment…</p>}
      {catalogue.isError && <p className="mt-2 text-sm">{catalogue.error.message}</p>}
      {!showForm && catalogue.data?.length === 0 && (
        <p className="mt-2 text-sm">No equipment in the catalogue yet.</p>
      )}
      {!showForm && catalogue.data && catalogue.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200" aria-label="Equipment catalogue entries">
          {catalogue.data
            .filter((equipment) =>
              matchesSearch(
                search,
                equipment.equipment_type,
                equipment.description ?? '',
                equipment.location,
                equipment.operational_status,
              ),
            )
            .map((equipment) => (
              <li
                key={equipment.id}
                className="flex flex-wrap items-start justify-between gap-4 py-3 text-sm"
              >
                <div>
                  <p className="font-medium">{equipment.equipment_type}</p>
                  <p className="text-slate-500">
                    <span className="font-medium text-slate-700">Description: </span>
                    {equipment.description ?? 'Not provided'}
                  </p>
                  <p className="text-slate-500">
                    <span className="font-medium text-slate-700">Available: </span>
                    {equipment.total_quantity}
                  </p>
                  <p className="text-slate-500">
                    <span className="font-medium text-slate-700">Location: </span>
                    {equipment.location}
                  </p>
                  <p className="text-slate-500">
                    <span className="font-medium text-slate-700">Operational status: </span>
                    {equipment.operational_status}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                    disabled={deactivate.isPending || save.isPending}
                    onClick={() => startEditing(equipment)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                    disabled={deactivate.isPending || save.isPending}
                    onClick={() => deactivate.mutate(equipment)}
                    aria-label={`Deactivate ${equipment.equipment_type}`}
                  >
                    Deactivate
                  </button>
                </div>
              </li>
            ))}
        </ul>
      )}
      {!showForm &&
        search &&
        catalogue.data &&
        !catalogue.data.some((equipment) =>
          matchesSearch(
            search,
            equipment.equipment_type,
            equipment.description ?? '',
            equipment.location,
            equipment.operational_status,
          ),
        ) && <p className="mt-5 text-sm text-slate-500">No equipment matches your search.</p>}

      {deactivationOutcome && (
        <p className="mt-3 text-sm text-red-700" role="status">
          {deactivationOutcome}
        </p>
      )}

      {showForm && (
        <form className="mt-4 space-y-3" noValidate onSubmit={submit}>
          <button type="button" className="cs-button-secondary mb-4" onClick={cancelEditing}>
            ← Back to equipment
          </button>
          <h2 className="text-3xl font-medium">
            {editing === null ? 'Add equipment' : 'Edit equipment'}
          </h2>
          <Field label="Equipment type" error={reasonFor('equipment_type')}>
            <input
              value={values.equipment_type}
              onChange={(event) => setValues({ ...values, equipment_type: event.target.value })}
            />
          </Field>
          <Field label="Description" error={reasonFor('description')}>
            <textarea
              value={values.description ?? ''}
              onChange={(event) =>
                setValues({ ...values, description: event.target.value || null })
              }
            />
          </Field>
          <Field label="Total quantity" error={reasonFor('total_quantity')}>
            <input
              type="number"
              min="0"
              step="1"
              value={values.total_quantity ?? ''}
              onChange={(event) =>
                setValues({
                  ...values,
                  total_quantity: event.target.value === '' ? null : Number(event.target.value),
                })
              }
            />
          </Field>
          <Field label="Location" error={reasonFor('location')}>
            <input
              value={values.location}
              onChange={(event) => setValues({ ...values, location: event.target.value })}
            />
          </Field>
          <Field label="Operational status" error={reasonFor('operational_status')}>
            <select
              value={values.operational_status}
              onChange={(event) =>
                setValues({
                  ...values,
                  operational_status: event.target.value as EquipmentInput['operational_status'],
                })
              }
            >
              <option value="">Select a status</option>
              {OPERATIONAL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex gap-2">
            <button type="submit" className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">
              {editing === null ? 'Add equipment' : 'Save changes'}
            </button>
            {editing !== null && (
              <button
                type="button"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={cancelEditing}
              >
                Cancel edit
              </button>
            )}
          </div>
        </form>
      )}
      {outcome && (
        <p className="mt-3 text-sm" role="status">
          {outcome}
        </p>
      )}
    </section>
  )
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      {label}
      {children && (
        <span className="mt-1 block [&_input]:w-full [&_input]:rounded [&_input]:border [&_input]:border-slate-300 [&_input]:p-2 [&_select]:w-full [&_select]:rounded [&_select]:border [&_select]:border-slate-300 [&_select]:p-2 [&_textarea]:w-full [&_textarea]:rounded [&_textarea]:border [&_textarea]:border-slate-300 [&_textarea]:p-2">
          {children}
        </span>
      )}
      {error && (
        <span className="mt-1 block text-red-700">
          {label} {error}
        </span>
      )}
    </label>
  )
}

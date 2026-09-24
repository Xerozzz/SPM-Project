import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  createVenueUnavailability,
  deleteVenueUnavailability,
  listVenueUnavailabilities,
  type Venue,
  type VenueUnavailability,
  type VenueUnavailabilityInput,
  type VenueProblem,
  updateVenueUnavailability,
  VenueUnavailabilityRejectedError,
} from '../api/venues'
import { useAuth } from '../auth/useAuth'

type FormValues = { startsAt: string; endsAt: string; reason: string }
const emptyValues: FormValues = { startsAt: '', endsAt: '', reason: '' }

/** SCRUM-62's management view. This is a list of closure records, not SCRUM-54's calendar. */
export default function VenueUnavailabilityManager({ venues }: { venues: Venue[] }) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [venueId, setVenueId] = useState('')
  const [editing, setEditing] = useState<VenueUnavailability | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [problems, setProblems] = useState<VenueProblem[]>([])
  const selectedVenue = venues.find((venue) => venue.id === venueId)
  const queryKey = ['venue-unavailabilities', token, venueId]
  const records = useQuery({
    queryKey,
    queryFn: () => listVenueUnavailabilities(token ?? '', venueId),
    enabled: token !== null && venueId !== '',
  })
  const refresh = () => void queryClient.invalidateQueries({ queryKey })
  const failed = (reason: Error) => {
    if (reason instanceof VenueUnavailabilityRejectedError) {
      setProblems(reason.problems)
      setError(null)
    } else {
      setProblems([])
      setError(reason.message)
    }
  }
  const saved = () => {
    setEditing(null)
    setError(null)
    setProblems([])
    refresh()
  }
  const save = useMutation({
    mutationFn: (input: VenueUnavailabilityInput) =>
      editing
        ? updateVenueUnavailability(token ?? '', venueId, editing.id, input)
        : createVenueUnavailability(token ?? '', venueId, input),
    onSuccess: saved,
    onError: failed,
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteVenueUnavailability(token ?? '', venueId, id),
    onSuccess: saved,
    onError: failed,
  })

  if (venues.length === 0) return null

  return (
    <section className="mt-6 border-t border-slate-200 pt-4">
      <h2 className="font-medium">Venue unavailability</h2>
      <p className="mt-1 text-sm text-slate-500">
        Record maintenance and closures. Calendar display will be added with SCRUM-54.
      </p>
      <label className="mt-3 block text-sm font-medium">
        Venue
        <select
          value={venueId}
          onChange={(event) => {
            setVenueId(event.target.value)
            setEditing(null)
            setError(null)
            setProblems([])
          }}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        >
          <option value="">Choose a venue</option>
          {venues.map((venue) => (
            <option key={venue.id} value={venue.id}>
              {venue.name}
            </option>
          ))}
        </select>
      </label>
      {venueId && (
        <UnavailabilityForm
          key={editing?.id ?? `${venueId}-new`}
          editing={editing}
          isSaving={save.isPending}
          problems={problems}
          onCancel={() => setEditing(null)}
          onSubmit={(input) => save.mutate(input)}
        />
      )}
      {venueId && <h3 className="mt-5 text-sm font-medium">Recorded unavailability periods</h3>}
      {records.isError && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {records.error.message}
        </p>
      )}
      {records.data?.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">No unavailability periods are recorded.</p>
      )}
      {records.data?.map((record) => (
        <div
          key={record.id}
          className="mt-3 flex justify-between gap-3 rounded bg-slate-50 p-3 text-sm"
        >
          <p>
            <span className="font-medium">{record.reason}</span>
            <br />
            {display(record.starts_at)} to {display(record.ends_at)}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setEditing(record)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => remove.mutate(record.id)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}
      {selectedVenue && (
        <p className="mt-3 text-xs text-slate-500">Changes apply to {selectedVenue.name} only.</p>
      )}
    </section>
  )
}

function UnavailabilityForm({
  editing,
  isSaving,
  problems,
  onCancel,
  onSubmit,
}: {
  editing: VenueUnavailability | null
  isSaving: boolean
  problems: VenueProblem[]
  onCancel: () => void
  onSubmit: (input: VenueUnavailabilityInput) => void
}) {
  const [values, setValues] = useState<FormValues>(editing ? valuesOf(editing) : emptyValues)
  const reasonFor = (field: string) => problems.find((problem) => problem.field === field)?.reason
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({
      starts_at: values.startsAt ? new Date(values.startsAt).toISOString() : null,
      ends_at: values.endsAt ? new Date(values.endsAt).toISOString() : null,
      reason: values.reason,
    })
  }
  return (
    <form className="mt-4 space-y-3" noValidate onSubmit={submit}>
      <label className="block text-sm font-medium">
        Start date and time
        <input
          required
          type="datetime-local"
          value={values.startsAt}
          onChange={(event) => setValues({ ...values, startsAt: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
        {reasonFor('starts_at') && (
          <ErrorMessage text={`Start date and time ${reasonFor('starts_at')}`} />
        )}
      </label>
      <label className="block text-sm font-medium">
        End date and time
        <input
          required
          type="datetime-local"
          value={values.endsAt}
          onChange={(event) => setValues({ ...values, endsAt: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
        {reasonFor('ends_at') && (
          <ErrorMessage text={`End date and time ${reasonFor('ends_at')}`} />
        )}
      </label>
      <label className="block text-sm font-medium">
        Reason
        <textarea
          required
          value={values.reason}
          onChange={(event) => setValues({ ...values, reason: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
        {reasonFor('reason') && <ErrorMessage text={`Reason ${reasonFor('reason')}`} />}
      </label>
      <button
        type="submit"
        disabled={isSaving}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {editing ? 'Save closure' : 'Record unavailability'}
      </button>
      {editing && (
        <button
          type="button"
          onClick={onCancel}
          className="ml-2 rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Cancel
        </button>
      )}
    </form>
  )
}

function ErrorMessage({ text }: { text: string }) {
  return <span className="mt-1 block text-sm font-normal text-red-600">{text}</span>
}

function valuesOf(record: VenueUnavailability): FormValues {
  return {
    startsAt: localDateTime(record.starts_at),
    endsAt: localDateTime(record.ends_at),
    reason: record.reason,
  }
}

function localDateTime(value: string): string {
  const date = new Date(value)
  const part = (number: number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())}T${part(date.getHours())}:${part(date.getMinutes())}`
}

function display(value: string): string {
  return new Date(value).toLocaleString()
}

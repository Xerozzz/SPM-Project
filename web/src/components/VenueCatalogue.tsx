import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  createVenue,
  deactivateVenue,
  listAllVenues,
  listVenues,
  reactivateVenue,
  ROOM_LAYOUTS,
  type Venue,
  type VenueInput,
  type VenueProblem,
  VenueRejectedError,
} from '../api/venues'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-59: the venue catalogue.
 *
 * Venue Staff see every venue and can add one or change its state; everyone else sees the
 * selectable catalogue read-only (AC2). Which list is fetched follows the caller's role,
 * and the server enforces the same split, so hiding a button is presentation and not the
 * authorisation rule.
 */
export default function VenueCatalogue() {
  const { token, hasRole } = useAuth()
  const queryClient = useQueryClient()
  const isStaff = hasRole('venue_staff')
  const [problems, setProblems] = useState<VenueProblem[]>([])
  const [outcome, setOutcome] = useState<string | null>(null)

  const queryKey = ['venues', isStaff ? 'all' : 'selectable', token]
  const venues = useQuery({
    queryKey,
    queryFn: () => (isStaff ? listAllVenues(token ?? '') : listVenues(token ?? '')),
    enabled: token !== null,
  })

  const refresh = () => void queryClient.invalidateQueries({ queryKey })

  function handleFailure(error: Error) {
    if (error instanceof VenueRejectedError) {
      setProblems(error.problems)
      setOutcome(null)
    } else {
      setProblems([])
      setOutcome(error.message)
    }
  }

  const add = useMutation({
    mutationFn: (venue: VenueInput) => createVenue(token ?? '', venue),
    onSuccess: (venue) => {
      setProblems([])
      setOutcome(`“${venue.name}” has been added to the catalogue.`)
      refresh()
    },
    onError: handleFailure,
  })

  const setActive = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      active ? reactivateVenue(token ?? '', id) : deactivateVenue(token ?? '', id),
    onSuccess: (venue) => {
      setProblems([])
      setOutcome(
        venue.is_active
          ? `“${venue.name}” is selectable again.`
          : `“${venue.name}” has been deactivated and can no longer be selected.`,
      )
      refresh()
    },
    onError: handleFailure,
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue catalogue</h2>
      <p className="mt-1 text-sm text-slate-500">
        {isStaff
          ? 'Add venues and take them out of use. Deactivated venues stay on existing events.'
          : 'Venues available for planning. Venue Staff maintain this list.'}
      </p>

      {venues.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {venues.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {venues.error.message}
        </p>
      )}
      {venues.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No venues in the catalogue yet.</p>
      )}

      {venues.data && venues.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200">
          {venues.data.map((venue) => (
            <VenueRow
              key={venue.id}
              venue={venue}
              canManage={isStaff}
              isBusy={setActive.isPending}
              onToggleActive={() => setActive.mutate({ id: venue.id, active: !venue.is_active })}
            />
          ))}
        </ul>
      )}

      {isStaff && (
        <AddVenueForm
          problems={problems}
          isSaving={add.isPending}
          onSubmit={(venue) => add.mutate(venue)}
        />
      )}

      {outcome && (
        <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          {outcome}
        </p>
      )}
    </section>
  )
}

function VenueRow({
  venue,
  canManage,
  isBusy,
  onToggleActive,
}: {
  venue: Venue
  canManage: boolean
  isBusy: boolean
  onToggleActive: () => void
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 py-3">
      <div>
        <p className="font-medium">
          {venue.name}
          {!venue.is_active && (
            <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
              Deactivated
            </span>
          )}
        </p>
        <p className="text-sm text-slate-500">
          {venue.location} · up to {venue.maximum_capacity} people · {shortTime(venue.opens_at)} to{' '}
          {shortTime(venue.closes_at)}
        </p>
        <p className="text-sm text-slate-500">Layouts: {venue.supported_layouts.join(', ')}</p>
        {venue.facilities.length > 0 && (
          <p className="text-sm text-slate-500">Facilities: {venue.facilities.join(', ')}</p>
        )}
        {venue.accessibility_features.length > 0 && (
          <p className="text-sm text-slate-500">
            Accessibility: {venue.accessibility_features.join(', ')}
          </p>
        )}
      </div>
      {canManage && (
        <button
          type="button"
          onClick={onToggleActive}
          disabled={isBusy}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {venue.is_active ? 'Deactivate' : 'Reactivate'}
        </button>
      )}
    </li>
  )
}

const emptyVenue: VenueInput = {
  name: '',
  location: '',
  maximum_capacity: null,
  facilities: [],
  supported_layouts: [],
  accessibility_features: [],
  opens_at: '',
  closes_at: '',
}

function AddVenueForm({
  problems,
  isSaving,
  onSubmit,
}: {
  problems: VenueProblem[]
  isSaving: boolean
  onSubmit: (venue: VenueInput) => void
}) {
  const [values, setValues] = useState<VenueInput>(emptyVenue)
  const reasonFor = (field: string) => problems.find((p) => p.field === field)?.reason

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({
      ...values,
      // datetime inputs give "HH:MM"; the API stores seconds too.
      opens_at: values.opens_at ? `${values.opens_at}:00` : '',
      closes_at: values.closes_at ? `${values.closes_at}:00` : '',
    })
  }

  function toggleLayout(layout: string) {
    setValues((current) => ({
      ...current,
      supported_layouts: current.supported_layouts.includes(layout)
        ? current.supported_layouts.filter((value) => value !== layout)
        : [...current.supported_layouts, layout],
    }))
  }

  return (
    <form className="mt-4 space-y-3 border-t border-slate-200 pt-4" noValidate onSubmit={submit}>
      <h3 className="text-sm font-medium">Add a venue</h3>

      <Field label="Name" error={reasonFor('name')}>
        <input
          value={values.name}
          onChange={(event) => setValues({ ...values, name: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <Field label="Location" error={reasonFor('location')}>
        <input
          value={values.location}
          onChange={(event) => setValues({ ...values, location: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <Field label="Maximum capacity" error={reasonFor('maximum_capacity')}>
        <input
          type="number"
          value={values.maximum_capacity ?? ''}
          onChange={(event) =>
            setValues({
              ...values,
              maximum_capacity: event.target.value === '' ? null : Number(event.target.value),
            })
          }
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <fieldset>
        <legend className="text-sm font-medium">Supported layouts</legend>
        <div className="mt-1 flex flex-wrap gap-3">
          {ROOM_LAYOUTS.map((layout) => (
            <label key={layout} className="text-sm">
              <input
                type="checkbox"
                checked={values.supported_layouts.includes(layout)}
                onChange={() => toggleLayout(layout)}
                className="mr-1"
              />
              {layout.replace('_', ' ')}
            </label>
          ))}
        </div>
        {reasonFor('supported_layouts') && (
          <p className="mt-1 text-sm text-red-600">
            Supported layouts {reasonFor('supported_layouts')}
          </p>
        )}
      </fieldset>

      <Field label="Opens at" error={reasonFor('opens_at')}>
        <input
          type="time"
          value={values.opens_at}
          onChange={(event) => setValues({ ...values, opens_at: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <Field label="Closes at" error={reasonFor('closes_at')}>
        <input
          type="time"
          value={values.closes_at}
          onChange={(event) => setValues({ ...values, closes_at: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <button
        type="submit"
        disabled={isSaving}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        Add venue
      </button>
    </form>
  )
}

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <label className="block text-sm font-medium">
      {label}
      {children}
      {error && (
        <span className="mt-1 block text-sm font-normal text-red-600">
          {label} {error}
        </span>
      )}
    </label>
  )
}

/** "08:00:00" reads better as "08:00" in a list. */
function shortTime(value: string): string {
  return value.slice(0, 5)
}

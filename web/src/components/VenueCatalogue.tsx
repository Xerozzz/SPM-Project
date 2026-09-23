import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  createVenue,
  listVenues,
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
 * Venue Staff add venues; everyone else reads the same catalogue without the form (AC2).
 * Changing and retiring a venue land with the story that adds them. The server enforces
 * the split too, so a missing control is presentation and not the authorisation rule.
 */
export default function VenueCatalogue() {
  const { token, hasRole } = useAuth()
  const queryClient = useQueryClient()
  const isStaff = hasRole('venue_staff')
  const [problems, setProblems] = useState<VenueProblem[]>([])
  const [outcome, setOutcome] = useState<string | null>(null)
  const queryKey = ['venues', token]
  const venues = useQuery({
    queryKey,
    queryFn: () => listVenues(token ?? ''),
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

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue catalogue</h2>
      <p className="mt-1 text-sm text-slate-500">
        {isStaff
          ? 'Add venues to the catalogue.'
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
            <VenueRow key={venue.id} venue={venue} />
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

function VenueRow({ venue }: { venue: Venue }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 py-3">
      <div>
        <p className="font-medium">{venue.name}</p>
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
    </li>
  )
}

/**
 * What the form holds while it is being filled in. Times are strings here because that is
 * what a time input gives, empty included; they become the API's `string | null` only on
 * submit. Same split as EventRequestFormValues in validation/eventRequest.ts.
 */
type VenueFormValues = Omit<VenueInput, 'opens_at' | 'closes_at'> & {
  opens_at: string
  closes_at: string
}

const emptyVenue: VenueFormValues = {
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
  const [values, setValues] = useState<VenueFormValues>(emptyVenue)
  const reasonFor = (field: string) => problems.find((p) => p.field === field)?.reason

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({
      ...values,
      // A time input gives "HH:MM" once filled, and "" while empty. Empty means the field
      // was not supplied, so it has to go as null: "" is not a time, and the API would
      // reject it with a parser error instead of the named-field problem AC5 asks for.
      opens_at: withSeconds(values.opens_at),
      closes_at: withSeconds(values.closes_at),
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

/** A time input's "HH:MM", as the API's "HH:MM:SS", or null when nothing was entered. */
function withSeconds(value: string): string | null {
  return value ? `${value}:00` : null
}

/** "08:00:00" reads better as "08:00" in a form and a list. */
function shortTime(value: string): string {
  return value.slice(0, 5)
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  createVenue,
  deactivateVenue,
  listVenues,
  ROOM_LAYOUTS,
  updateVenue,
  type Venue,
  type VenueInput,
  type VenueProblem,
  VenueRejectedError,
  type UpdatedVenue,
} from '../api/venues'
import { useAuth } from '../auth/useAuth'
import VenueUnavailabilityManager from './VenueUnavailabilityManager'

/**
 * SCRUM-59: the venue catalogue.
 *
 * Venue Staff add venues, change their details and take them out of use; everyone else
 * reads the same catalogue without those controls (AC2). The server enforces the split
 * too, so hiding a button is presentation and not the authorisation rule.
 */
export default function VenueCatalogue() {
  const { token, hasRole } = useAuth()
  const queryClient = useQueryClient()
  const isStaff = hasRole('venue_staff')
  const [problems, setProblems] = useState<VenueProblem[]>([])
  const [outcome, setOutcome] = useState<string | null>(null)
  /** The venue being edited, or null when the form is adding a new one. */
  const [editing, setEditing] = useState<Venue | null>(null)

  const queryKey = ['venues', token]
  const venues = useQuery({
    queryKey,
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null,
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey })
    // SCRUM-89: changing a venue's buffers changes which bookings can stand, and the
    // panel showing those sits on this same page. Without this it keeps saying nothing
    // needs attention directly below a save that just caused some.
    void queryClient.invalidateQueries({ queryKey: ['booking-problems', token] })
  }

  function handleFailure(error: Error) {
    if (error instanceof VenueRejectedError) {
      setProblems(error.problems)
      setOutcome(null)
    } else {
      setProblems([])
      setOutcome(error.message)
    }
  }

  /** Every successful save clears the form state and reports what happened. */
  function handleSaved(message: string) {
    setProblems([])
    setEditing(null)
    setOutcome(message)
    refresh()
  }

  const save = useMutation({
    mutationFn: ({ id, venue }: { id: string | null; venue: VenueInput }) =>
      id ? updateVenue(token ?? '', id, venue) : createVenue(token ?? '', venue),
    onSuccess: (venue, { id }) =>
      handleSaved(
        id
          ? `“${venue.name}” has been updated.${describeBufferChange(venue)}`
          : `“${venue.name}” has been added to the catalogue.`,
      ),
    onError: handleFailure,
  })

  const deactivate = useMutation({
    mutationFn: (id: string) => deactivateVenue(token ?? '', id),
    onSuccess: (venue) =>
      handleSaved(`“${venue.name}” has been deactivated and can no longer be selected.`),
    onError: handleFailure,
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue catalogue</h2>
      <p className="mt-1 text-sm text-slate-500">
        {isStaff
          ? 'Add venues, change their details, and take them out of use.'
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
              isBusy={deactivate.isPending || save.isPending}
              onEdit={() => {
                setProblems([])
                setOutcome(null)
                setEditing(venue)
              }}
              onDeactivate={() => deactivate.mutate(venue.id)}
            />
          ))}
        </ul>
      )}

      {isStaff && (
        <VenueForm
          key={editing?.id ?? 'new'}
          editing={editing}
          problems={problems}
          isSaving={save.isPending}
          onCancel={() => {
            setEditing(null)
            setProblems([])
          }}
          onSubmit={(venue) => save.mutate({ id: editing?.id ?? null, venue })}
        />
      )}

      {isStaff && venues.data && <VenueUnavailabilityManager venues={venues.data} />}

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
  onEdit,
  onDeactivate,
}: {
  venue: Venue
  canManage: boolean
  isBusy: boolean
  onEdit: () => void
  onDeactivate: () => void
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 py-3">
      <div>
        <p className="font-medium">{venue.name}</p>
        <p className="text-sm text-slate-500">
          {venue.location} · up to {venue.maximum_capacity} people · {shortTime(venue.opens_at)} to{' '}
          {shortTime(venue.closes_at)}
          {describeBuffers(venue)}
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
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onEdit}
            disabled={isBusy}
            aria-label={`Edit ${venue.name}`}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDeactivate}
            disabled={isBusy}
            aria-label={`Deactivate ${venue.name}`}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Deactivate
          </button>
        </div>
      )}
    </li>
  )
}

/**
 * What the form holds while it is being filled in. Times are strings here because that is
 * what a time input gives, empty included; they become the API's `string | null` only on
 * submit. The two list fields are strings for the same reason: the user is part way through
 * typing "Projector, Hearing loop" for most of the time the form is open, and splitting on
 * every keystroke would throw away the comma they just pressed. Same split as
 * EventRequestFormValues in validation/eventRequest.ts.
 */
type VenueFormValues = Omit<
  VenueInput,
  'opens_at' | 'closes_at' | 'facilities' | 'accessibility_features'
> & {
  opens_at: string
  closes_at: string
  facilities: string
  accessibility_features: string
}

const emptyVenue: VenueFormValues = {
  name: '',
  location: '',
  maximum_capacity: null,
  facilities: '',
  supported_layouts: [],
  accessibility_features: '',
  opens_at: '',
  closes_at: '',
  setup_minutes: null,
  turnaround_minutes: null,
}

/**
 * SCRUM-89 AC6: what a save did to the venue's existing bookings, if it moved the buffers.
 *
 * Says so explicitly when nothing was affected, because silence after changing a setup or
 * turnaround time reads as "not checked" rather than "checked and fine". Returns nothing
 * at all when the save did not touch the buffers, since there was nothing to check.
 */
function describeBufferChange(venue: Venue | UpdatedVenue): string {
  if (!('buffer_change' in venue) || !venue.buffer_change.changed) return ''
  const count = venue.buffer_change.problems.length
  if (count === 0) return ' No existing bookings are affected.'
  return ` ${count} existing booking${count === 1 ? '' : 's'} can no longer fit and ${
    count === 1 ? 'is' : 'are'
  } listed under bookings needing attention.`
}

/** An existing venue as the form holds it: "HH:MM:SS" from the API becomes "HH:MM". */
function formValuesOf(venue: Venue): VenueFormValues {
  return {
    name: venue.name,
    location: venue.location,
    maximum_capacity: venue.maximum_capacity,
    // The form holds these two as one comma-separated line, so they go back the way
    // asList() reads them. Handing over the array would wipe them on the next save.
    facilities: venue.facilities.join(', '),
    supported_layouts: [...venue.supported_layouts],
    accessibility_features: venue.accessibility_features.join(', '),
    opens_at: shortTime(venue.opens_at),
    closes_at: shortTime(venue.closes_at),
    setup_minutes: venue.setup_minutes,
    turnaround_minutes: venue.turnaround_minutes,
  }
}

function VenueForm({
  editing,
  problems,
  isSaving,
  onSubmit,
  onCancel,
}: {
  editing: Venue | null
  problems: VenueProblem[]
  isSaving: boolean
  onSubmit: (venue: VenueInput) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<VenueFormValues>(
    editing ? formValuesOf(editing) : emptyVenue,
  )
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
      facilities: asList(values.facilities),
      accessibility_features: asList(values.accessibility_features),
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
      <h3 className="text-sm font-medium">{editing ? `Edit “${editing.name}”` : 'Add a venue'}</h3>

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

      <Field
        label="Setup time (minutes)"
        error={reasonFor('setup_minutes')}
        hint="Time needed to prepare the venue before an event. It is occupied for this long beforehand."
      >
        <input
          type="number"
          min={0}
          value={values.setup_minutes ?? ''}
          onChange={(event) =>
            setValues({
              ...values,
              setup_minutes: event.target.value === '' ? null : Number(event.target.value),
            })
          }
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
        />
      </Field>

      <Field
        label="Turnaround time (minutes)"
        error={reasonFor('turnaround_minutes')}
        hint="Time needed to reset the venue afterwards. It stays occupied for this long."
      >
        <input
          type="number"
          min={0}
          value={values.turnaround_minutes ?? ''}
          onChange={(event) =>
            setValues({
              ...values,
              turnaround_minutes: event.target.value === '' ? null : Number(event.target.value),
            })
          }
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

      <Field label="Facilities" error={reasonFor('facilities')}>
        <input
          value={values.facilities}
          onChange={(event) => setValues({ ...values, facilities: event.target.value })}
          placeholder="Projector, Hearing loop"
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm font-normal"
        />
      </Field>

      <Field label="Accessibility features" error={reasonFor('accessibility_features')}>
        <input
          value={values.accessibility_features}
          onChange={(event) => setValues({ ...values, accessibility_features: event.target.value })}
          placeholder="Step-free access, Accessible toilet"
          className="mt-1 w-full rounded border border-slate-300 p-2 text-sm font-normal"
        />
      </Field>

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

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {editing ? 'Save changes' : 'Add venue'}
        </button>
        {editing && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string
  error?: string
  /** Shown under the label. For a field whose effect is not obvious from its name. */
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block text-sm font-medium">
      {label}
      {hint && <span className="block text-sm font-normal text-slate-500">{hint}</span>}
      {children}
      {error && (
        <span className="mt-1 block text-sm font-normal text-red-600">
          {label} {error}
        </span>
      )}
    </label>
  )
}

/**
 * A comma-separated list as the API's array. Blanks are dropped, so trailing commas and
 * "a,,b" behave, and an empty box means the venue simply has none of these.
 */
function asList(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

/** A time input's "HH:MM", as the API's "HH:MM:SS", or null when nothing was entered. */
function withSeconds(value: string): string | null {
  return value ? `${value}:00` : null
}

/** "08:00:00" reads better as "08:00" in a form and a list. */
function shortTime(value: string): string {
  return value.slice(0, 5)
}

/**
 * SCRUM-82: the venue's buffers, for the catalogue line, or nothing when it has none.
 *
 * Left out entirely for a venue with no buffers rather than shown as "0 min setup",
 * because zero buffers is the normal case and means the venue behaves as it always did.
 */
function describeBuffers(venue: Venue): string {
  const parts: string[] = []
  if (venue.setup_minutes > 0) parts.push(`${venue.setup_minutes} min setup`)
  if (venue.turnaround_minutes > 0) parts.push(`${venue.turnaround_minutes} min turnaround`)
  return parts.length > 0 ? ` · ${parts.join(', ')}` : ''
}

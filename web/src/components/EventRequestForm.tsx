import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'

import {
  createDraft,
  createEventRequest,
  type EventRequest,
  EventRequestValidationError,
  listEquipmentRequirementTypes,
  listVenueRequirementNames,
  type EventRequestCreate,
  type EventRequestDraftInput,
  FIELD_LABELS,
  submitEventRequest,
  updateDraft,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import {
  type EventRequestFieldErrors,
  type EventRequestFieldName,
  type EventRequestFormValues,
  validateEventRequest,
} from '../validation/eventRequest'

type FormValues = EventRequestFormValues
type FieldName = EventRequestFieldName
type FieldErrors = EventRequestFieldErrors

const initialValues: FormValues = {
  name: '',
  purpose: '',
  description: '',
  start_at: '',
  end_at: '',
  expected_attendance: '',
  venue_requirement: '',
  accessibility_requirement: '',
  equipment_requirement: '',
  layout_requirement: '',
  registration_requirement: '',
}

const textFields: Array<{
  name: Exclude<
    FieldName,
    'start_at' | 'end_at' | 'expected_attendance' | 'venue_requirement' | 'equipment_requirement'
  >
  multiline?: boolean
}> = [
  { name: 'name' },
  { name: 'purpose', multiline: true },
  { name: 'description', multiline: true },
  { name: 'accessibility_requirement', multiline: true },
  { name: 'layout_requirement', multiline: true },
  { name: 'registration_requirement', multiline: true },
]

/**
 * SCRUM-28: collect a new event request. Catalogue selections describe needs; they never
 * reserve resources.
 */
export default function EventRequestForm({
  editing = null,
  onDone = () => {},
}: {
  /** A draft the organiser chose to edit. Null means a new request. */
  editing?: EventRequest | null
  /** Return to My Events, with a confirmation after a successful save or submission. */
  onDone?: (message?: string) => void
} = {}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [values, setValues] = useState<FormValues>(initialValues)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  // Survives a failed submit so the retry patches that request instead of making
  // another. Not state: nothing renders from it.
  const started = useRef<string | null>(null)
  const section = useRef<HTMLElement>(null)
  // Reloads the fields when a different draft is chosen. Keyed on the id rather than the
  // object, so re-rendering the list does not throw away what is being typed.
  const [loadedId, setLoadedId] = useState<string | null>(null)
  if ((editing?.id ?? null) !== loadedId) {
    setLoadedId(editing?.id ?? null)
    setValues(editing ? formValuesOf(editing) : initialValues)
    setErrors({})
    // Only when a draft is being loaded in. A save releases the form by clearing
    // `editing`, which comes back through here in the same pass, and clearing the
    // message unconditionally would wipe the confirmation that save just set.
    if (editing) setOutcome(null)
    started.current = null
  }
  // Focus the name when opening the form or choosing a different draft. Using the id
  // keeps list refreshes from interrupting someone who is typing.
  const editingId = editing?.id ?? null
  useEffect(() => {
    section.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    // Moving focus is what tells a keyboard or screen reader user the form is now theirs;
    // the scroll only helps people who can see it.
    section.current?.querySelector<HTMLInputElement>('#name')?.focus({ preventScroll: true })
  }, [editingId])

  const equipmentTypes = useQuery({
    queryKey: ['equipment-types', token],
    queryFn: () => listEquipmentRequirementTypes(token ?? ''),
    enabled: token !== null,
  })
  const venueNames = useQuery({
    queryKey: ['venue-names', token],
    queryFn: () => listVenueRequirementNames(token ?? ''),
    enabled: token !== null,
  })

  /** Everything a successful save has to refresh, wherever it came from. */
  function refreshLists() {
    void queryClient.invalidateQueries({ queryKey: ['event-requests', 'mine', token] })
    void queryClient.invalidateQueries({ queryKey: ['organisation-calendar', token] })
  }

  function showProblems(error: Error) {
    if (error instanceof EventRequestValidationError) {
      setErrors((current) => ({
        ...current,
        ...Object.fromEntries(error.problems.map((problem) => [problem.field, problem.reason])),
      }))
    }
  }

  /**
   * The primary action: a request the organiser is finished with goes straight for
   * review. Creating and submitting are two calls because the API keeps them separate,
   * but there is no state in between that the organiser ever sees.
   */
  const createRequest = useMutation({
    mutationFn: async (request: EventRequestCreate) => {
      // The request this press is about: the draft being edited, or the one an earlier
      // press already created. Without the second case a submit that fails leaves a
      // request behind and the retry creates another, so one press becomes two records.
      const existing = editing?.id ?? started.current
      const saved = existing
        ? await updateDraft(token ?? '', existing, request as EventRequestDraftInput)
        : await createEventRequest(token ?? '', request)
      started.current = saved.id
      return submitEventRequest(token ?? '', saved.id)
    },
    onError: showProblems,
    onSuccess: (request) => {
      started.current = null
      setValues(initialValues)
      setErrors({})
      refreshLists()
      setOutcome(`“${request.name}” has been submitted for review.`)
      onDone(`“${request.name}” has been submitted for review.`)
    },
  })

  /**
   * The quieter action: keep what has been typed without asking anyone to look at it.
   * Saved without the completeness check, because a draft is allowed to be unfinished;
   * the check runs when it is submitted.
   */
  const saveDraft = useMutation({
    mutationFn: (draft: EventRequestDraftInput) => {
      const existing = editing?.id ?? started.current
      return existing ? updateDraft(token ?? '', existing, draft) : createDraft(token ?? '', draft)
    },
    onError: showProblems,
    onSuccess: (request) => {
      started.current = null
      setValues(initialValues)
      setErrors({})
      refreshLists()
      setOutcome(`“${request.name || 'Untitled request'}” has been saved as a draft.`)
      onDone(`“${request.name || 'Untitled request'}” has been saved as a draft.`)
    },
  })

  function change(name: FieldName, value: string) {
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: undefined }))
    setOutcome(null)
  }

  function requestBody(): EventRequestCreate | null {
    const validationErrors = validateEventRequest(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return null

    return {
      ...values,
      expected_attendance: Number(values.expected_attendance),
      // datetime-local has no offset. Convert it at the browser boundary so the API receives
      // the timezone-aware UTC value required by AGENTS.md.
      start_at: new Date(values.start_at).toISOString(),
      end_at: new Date(values.end_at).toISOString(),
    }
  }

  function draftBody(): EventRequestDraftInput {
    // A draft is allowed to be unfinished, so nothing is validated here and an empty
    // field is sent as null rather than "": the API stores absence, not a blank string.
    const text = (value: string) => (value.trim() === '' ? null : value)
    return {
      name: text(values.name),
      purpose: text(values.purpose),
      description: text(values.description),
      start_at: values.start_at === '' ? null : new Date(values.start_at).toISOString(),
      end_at: values.end_at === '' ? null : new Date(values.end_at).toISOString(),
      expected_attendance:
        values.expected_attendance === '' ? null : Number(values.expected_attendance),
      venue_requirement: text(values.venue_requirement),
      accessibility_requirement: text(values.accessibility_requirement),
      equipment_requirement: text(values.equipment_requirement),
      layout_requirement: text(values.layout_requirement),
      registration_requirement: text(values.registration_requirement),
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const request = requestBody()
    if (!request) return
    // Whichever button is pressed owns the message area, so the other one's last
    // failure does not sit there contradicting the result of this press.
    saveDraft.reset()
    createRequest.mutate(request)
  }

  function save() {
    createRequest.reset()
    saveDraft.mutate(draftBody())
  }

  return (
    <section ref={section} className="cs-panel mt-6">
      <div className="border-b border-slate-100 pb-4">
        <h2 className="text-3xl font-medium tracking-[-0.04em] text-[#202124]">
          {editing ? 'Edit draft' : 'New event request'}
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Fields marked * are required to submit a request. A draft can be saved without them.
        </p>
      </div>
      <form className="mt-4 space-y-4" noValidate onSubmit={create}>
        {textFields.map(({ name, multiline }) => (
          <Field key={name} name={name} error={errors[name]}>
            {multiline ? (
              <textarea
                id={name}
                value={values[name]}
                onChange={(event) => change(name, event.target.value)}
                className="cs-field min-h-24 resize-y"
              />
            ) : (
              <input
                id={name}
                value={values[name]}
                onChange={(event) => change(name, event.target.value)}
                className="cs-field"
              />
            )}
          </Field>
        ))}
        <CatalogueRequirementField
          name="venue_requirement"
          options={venueNames.data ?? []}
          placeholder="Select a venue"
          value={values.venue_requirement}
          error={errors.venue_requirement}
          onChange={(value) => change('venue_requirement', value)}
        />
        <CatalogueRequirementField
          name="equipment_requirement"
          options={equipmentTypes.data ?? []}
          placeholder="Select equipment"
          value={values.equipment_requirement}
          error={errors.equipment_requirement}
          onChange={(value) => change('equipment_requirement', value)}
        />
        {(equipmentTypes.isError || venueNames.isError) && (
          <p role="alert" className="text-sm text-red-600">
            {equipmentTypes.error?.message ?? venueNames.error?.message}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <Field name="start_at" error={errors.start_at}>
            <input
              id="start_at"
              type="datetime-local"
              value={values.start_at}
              onChange={(event) => change('start_at', event.target.value)}
              className="cs-field"
            />
          </Field>
          <Field name="end_at" error={errors.end_at}>
            <input
              id="end_at"
              type="datetime-local"
              value={values.end_at}
              onChange={(event) => change('end_at', event.target.value)}
              className="cs-field"
            />
          </Field>
        </div>
        <Field name="expected_attendance" error={errors.expected_attendance}>
          <input
            id="expected_attendance"
            type="number"
            min="1"
            step="1"
            value={values.expected_attendance}
            onChange={(event) => change('expected_attendance', event.target.value)}
            className="cs-field"
          />
        </Field>
        {/* Both buttons, not just the first: a Save draft that the API refuses used to
            fail silently, because `createDraft` throws a plain error that the field-level
            handler has nothing to do with. */}
        {(createRequest.error ?? saveDraft.error) && (
          <p
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {(createRequest.error ?? saveDraft.error)?.message}. Your entered details are still
            available to edit.
          </p>
        )}
        {outcome && (
          <p
            role="status"
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
          >
            {outcome}
          </p>
        )}
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          <button
            type="submit"
            disabled={createRequest.isPending || saveDraft.isPending}
            className="cs-button"
          >
            {editing ? 'Submit for review' : 'Create event request'}
          </button>
          <button
            type="button"
            onClick={save}
            disabled={createRequest.isPending || saveDraft.isPending}
            className="cs-button-secondary"
          >
            Save draft
          </button>
          {editing && (
            <button type="button" onClick={() => onDone()} className="cs-button-secondary">
              Cancel
            </button>
          )}
        </div>
      </form>
    </section>
  )
}

/** An existing draft as the form holds it. */
function formValuesOf(request: EventRequest): FormValues {
  return {
    name: request.name ?? '',
    purpose: request.purpose ?? '',
    description: request.description ?? '',
    start_at: toDateTimeLocal(request.start_at),
    end_at: toDateTimeLocal(request.end_at),
    expected_attendance: request.expected_attendance?.toString() ?? '',
    venue_requirement: request.venue_requirement ?? '',
    accessibility_requirement: request.accessibility_requirement ?? '',
    equipment_requirement: request.equipment_requirement ?? '',
    layout_requirement: request.layout_requirement ?? '',
    registration_requirement: request.registration_requirement ?? '',
  }
}

/**
 * The stored UTC instant as a `datetime-local` input wants it: local wall clock, no
 * offset, to the minute. `requestBody` converts it back at the same boundary.
 */
function toDateTimeLocal(value: string | null): string {
  if (!value) return ''
  const at = new Date(value)
  const local = new Date(at.getTime() - at.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function CatalogueRequirementField({
  name,
  options,
  placeholder,
  value,
  error,
  onChange,
}: {
  name: 'venue_requirement' | 'equipment_requirement'
  options: readonly string[]
  placeholder: string
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  return (
    <Field name={name} error={error}>
      <select
        id={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="cs-field"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <p className="mt-1 text-sm text-slate-500">
        This records a requirement only; it does not reserve a specific resource.
      </p>
    </Field>
  )
}

function Field({
  name,
  error,
  children,
}: {
  name: FieldName
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={name} className="mb-1 block text-sm font-medium text-slate-700">
        {FIELD_LABELS[name]} *
      </label>
      {children}
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}

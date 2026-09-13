import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useState } from 'react'

import {
  createEventRequest,
  type EventRequestCreate,
  FIELD_LABELS,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

type FormValues = Omit<EventRequestCreate, 'expected_attendance' | 'start_at' | 'end_at'> & {
  expected_attendance: string
  start_at: string
  end_at: string
}

type FieldName = keyof FormValues
type FieldErrors = Partial<Record<FieldName, string>>

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

// These are requirement categories from the initial ConnectSphere catalogue, not individual
// rooms or equipment items. Saving one describes a need for later review; it cannot allocate
// a resource at this draft stage.
const venueRequirementOptions = [
  'Auditorium-type venue',
  'Lecture theatre-type venue',
  'Seminar room-type venue',
  'Outdoor event space',
]
const equipmentRequirementOptions = [
  'Projector-type requirement',
  'Microphone-type requirement',
  'PA system-type requirement',
  'Display screen-type requirement',
]

/**
 * SCRUM-28: collect a new event request. The venue and equipment fields describe needs;
 * they never choose catalogue items or reserve resources. The API remains the authority
 * for creating the Draft status.
 */
export default function EventRequestForm() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [values, setValues] = useState<FormValues>(initialValues)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [createdName, setCreatedName] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (request: EventRequestCreate) => createEventRequest(token ?? '', request),
    onSuccess: (request) => {
      setValues(initialValues)
      setErrors({})
      void queryClient.invalidateQueries({ queryKey: ['event-requests', 'mine', token] })
      setCreatedName(request.name)
    },
  })

  function change(name: FieldName, value: string) {
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: undefined }))
    setCreatedName(null)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    create.mutate({
      ...values,
      expected_attendance: Number(values.expected_attendance),
      // datetime-local has no offset. Convert it at the browser boundary so the API receives
      // the timezone-aware UTC value required by AGENTS.md.
      start_at: new Date(values.start_at).toISOString(),
      end_at: new Date(values.end_at).toISOString(),
    })
  }

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">New event request</h2>
      <p className="mt-1 text-sm text-slate-500">
        Fields marked * are required before a request can be submitted.
      </p>
      <form className="mt-4 space-y-4" noValidate onSubmit={submit}>
        {textFields.map(({ name, multiline }) => (
          <Field key={name} name={name} error={errors[name]}>
            {multiline ? (
              <textarea
                id={name}
                value={values[name]}
                onChange={(event) => change(name, event.target.value)}
                className="min-h-20 w-full rounded border border-slate-300 p-2"
              />
            ) : (
              <input
                id={name}
                value={values[name]}
                onChange={(event) => change(name, event.target.value)}
                className="w-full rounded border border-slate-300 p-2"
              />
            )}
          </Field>
        ))}
        <CatalogueRequirementField
          name="venue_requirement"
          options={venueRequirementOptions}
          placeholder="Select a venue"
          value={values.venue_requirement}
          error={errors.venue_requirement}
          onChange={(value) => change('venue_requirement', value)}
        />
        <CatalogueRequirementField
          name="equipment_requirement"
          options={equipmentRequirementOptions}
          placeholder="Select equipment"
          value={values.equipment_requirement}
          error={errors.equipment_requirement}
          onChange={(value) => change('equipment_requirement', value)}
        />
        <div className="space-y-4">
          <Field name="start_at" error={errors.start_at}>
            <input
              id="start_at"
              type="datetime-local"
              value={values.start_at}
              onChange={(event) => change('start_at', event.target.value)}
              className="w-full rounded border border-slate-300 p-2"
            />
          </Field>
          <Field name="end_at" error={errors.end_at}>
            <input
              id="end_at"
              type="datetime-local"
              value={values.end_at}
              onChange={(event) => change('end_at', event.target.value)}
              className="w-full rounded border border-slate-300 p-2"
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
            className="w-full rounded border border-slate-300 p-2"
          />
        </Field>
        {create.isError && (
          <p role="alert" className="text-sm text-red-600">
            {create.error.message}. Your entered details are still available to edit.
          </p>
        )}
        {createdName && (
          <p role="status" className="text-sm text-green-700">
            “{createdName}” was saved as a Draft. It has not been submitted for review.
          </p>
        )}
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Save draft
        </button>
      </form>
    </section>
  )
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
  options: string[]
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
        className="w-full rounded border border-slate-300 p-2"
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
      <label htmlFor={name} className="mb-1 block text-sm font-medium">
        {FIELD_LABELS[name]} *
      </label>
      {children}
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}

function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {}
  for (const [name, value] of Object.entries(values)) {
    if (!value.trim()) errors[name as FieldName] = 'This field is required.'
  }
  const attendance = Number(values.expected_attendance)
  if (values.expected_attendance && (!Number.isInteger(attendance) || attendance <= 0)) {
    errors.expected_attendance = 'Enter a positive whole number.'
  }
  if (values.start_at && values.end_at && new Date(values.end_at) <= new Date(values.start_at)) {
    errors.end_at = 'End date and time must be after the start date and time.'
  }
  return errors
}

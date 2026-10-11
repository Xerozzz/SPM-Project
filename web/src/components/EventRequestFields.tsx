import type { ReactNode } from 'react'

import { EQUIPMENT_REQUIREMENTS, FIELD_LABELS, VENUE_REQUIREMENTS } from '../api/eventRequests'
import type {
  EventRequestFieldErrors,
  EventRequestFieldName,
  EventRequestFormValues,
} from '../validation/eventRequest'

interface Props {
  idPrefix: string
  values: EventRequestFormValues
  errors?: EventRequestFieldErrors
  onChange: (name: EventRequestFieldName, value: string) => void
}

const textFields: Array<{
  name: Exclude<
    EventRequestFieldName,
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

/** Shared controls for new requests and resumed drafts. */
export default function EventRequestFields({ idPrefix, values, errors = {}, onChange }: Props) {
  return (
    <div className="space-y-4">
      {textFields.map(({ name, multiline }) => (
        <Field key={name} id={`${idPrefix}-${name}`} name={name} error={errors[name]}>
          {multiline ? (
            <textarea
              id={`${idPrefix}-${name}`}
              value={values[name]}
              onChange={(event) => onChange(name, event.target.value)}
              className="min-h-20 w-full rounded border border-slate-300 p-2"
            />
          ) : (
            <input
              id={`${idPrefix}-${name}`}
              value={values[name]}
              onChange={(event) => onChange(name, event.target.value)}
              className="w-full rounded border border-slate-300 p-2"
            />
          )}
        </Field>
      ))}
      <CatalogueRequirementField
        idPrefix={idPrefix}
        name="venue_requirement"
        options={VENUE_REQUIREMENTS}
        placeholder="Select a venue requirement"
        value={values.venue_requirement}
        error={errors.venue_requirement}
        onChange={(value) => onChange('venue_requirement', value)}
      />
      <CatalogueRequirementField
        idPrefix={idPrefix}
        name="equipment_requirement"
        options={EQUIPMENT_REQUIREMENTS}
        placeholder="Select an equipment requirement"
        value={values.equipment_requirement}
        error={errors.equipment_requirement}
        onChange={(value) => onChange('equipment_requirement', value)}
      />
      <Field id={`${idPrefix}-start_at`} name="start_at" error={errors.start_at}>
        <input
          id={`${idPrefix}-start_at`}
          type="datetime-local"
          step="1"
          value={values.start_at}
          onChange={(event) => onChange('start_at', event.target.value)}
          className="w-full rounded border border-slate-300 p-2"
        />
      </Field>
      <Field id={`${idPrefix}-end_at`} name="end_at" error={errors.end_at}>
        <input
          id={`${idPrefix}-end_at`}
          type="datetime-local"
          step="1"
          value={values.end_at}
          onChange={(event) => onChange('end_at', event.target.value)}
          className="w-full rounded border border-slate-300 p-2"
        />
      </Field>
      <Field
        id={`${idPrefix}-expected_attendance`}
        name="expected_attendance"
        error={errors.expected_attendance}
      >
        <input
          id={`${idPrefix}-expected_attendance`}
          type="number"
          min="1"
          step="1"
          value={values.expected_attendance}
          onChange={(event) => onChange('expected_attendance', event.target.value)}
          className="w-full rounded border border-slate-300 p-2"
        />
      </Field>
    </div>
  )
}

function CatalogueRequirementField({
  idPrefix,
  name,
  options,
  placeholder,
  value,
  error,
  onChange,
}: {
  idPrefix: string
  name: 'venue_requirement' | 'equipment_requirement'
  options: readonly string[]
  placeholder: string
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  const id = `${idPrefix}-${name}`
  return (
    <Field id={id} name={name} error={error}>
      <select
        id={id}
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
  id,
  name,
  error,
  children,
}: {
  id: string
  name: EventRequestFieldName
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {FIELD_LABELS[name]} *
      </label>
      {children}
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}

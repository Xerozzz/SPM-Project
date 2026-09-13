import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  createDraft,
  type EventRequest,
  type EventRequestDraftInput,
  FIELD_LABELS,
  type FieldProblem,
  getEventRequest,
  listDraftEventRequests,
  listMyEventRequests,
  submitEventRequest,
  SubmissionRejectedError,
  updateDraft,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import ClarificationThread from './ClarificationThread'

/**
 * SCRUM-46: an organiser's event requests, each with a Submit action while it is a draft.
 * Submitting a complete draft shows confirmation (AC1); an incomplete one lists the fields
 * to fix (AC2); a submitted request shows it is locked (AC3). No business rules live here —
 * the API decides, this component only shows the outcome.
 *
 * SCRUM-35: what to offer comes from the request's `status_permits`, so the status machine
 * stays the only place that knows what a status permits. Submit and edit are separate
 * permissions, so the locked message keys off `edit`, not off the absence of `submit`.
 * SCRUM-46/SCRUM-29: an organiser's event requests. Draft completeness and submission
 * rules live in the API; this component only sends organiser actions and shows outcomes.
 */
export default function MyEventRequests() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [editing, setEditing] = useState<EditingState | null>(null)

  // The token is part of the key: the list is per-user, and without it a sign-out and
  // sign-in as someone else on the same tab could briefly show the previous user's data
  // from the cache.
  const queryKey = ['event-requests', 'mine', token]
  const draftsQueryKey = ['event-requests', 'drafts', token]
  const requests = useQuery({
    queryKey,
    queryFn: () => listMyEventRequests(token ?? ''),
    enabled: token !== null,
  })
  const visibleDrafts = useQuery({
    queryKey: draftsQueryKey,
    queryFn: () => listDraftEventRequests(token ?? ''),
    enabled: token !== null,
  })

  const ownIds = new Set(requests.data?.map((request) => request.id) ?? [])

  // The mutation variable carries the request id plus its current name, so validation
  // feedback can name the request even when the API refuses submission.
  const submit = useMutation({
    mutationFn: (request: SubmitTarget) => submitEventRequest(token ?? '', request.id),
    onSuccess: (request) => {
      setOutcome({ kind: 'submitted', request })
      setEditing((current) =>
        current?.id === request.id
          ? {
              id: request.id,
              status: request.status,
              status_permits: request.status_permits,
              values: toForm(request),
            }
          : current,
      )
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({ queryKey: draftsQueryKey })
    },
    onError: (error, request) => {
      if (error instanceof SubmissionRejectedError) {
        setOutcome({ kind: 'incomplete', name: request.name, problems: error.problems })
      } else {
        setOutcome({ kind: 'failed', message: error.message })
      }
    },
  })

  const reopen = useMutation({
    mutationFn: (id: string) => getEventRequest(token ?? '', id),
    onSuccess: (request) => {
      setOutcome(null)
      setEditing({
        id: request.id,
        status: request.status,
        status_permits: request.status_permits,
        values: toForm(request),
      })
    },
    onError: (error) => {
      setOutcome({ kind: 'failed', message: error.message })
    },
  })

  const saveDraft = useMutation({
    mutationFn: (state: EditingState) => {
      const payload = toDraftPayload(state.values)
      return state.id === null
        ? createDraft(token ?? '', payload)
        : updateDraft(token ?? '', state.id, payload)
    },
    onSuccess: (request) => {
      setOutcome({ kind: 'saved', request })
      setEditing({
        id: request.id,
        status: request.status,
        status_permits: request.status_permits,
        values: toForm(request),
      })
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({ queryKey: draftsQueryKey })
    },
    onError: (error) => {
      setOutcome({ kind: 'failed', message: error.message })
    },
  })

  return (
    <section className="mt-6 space-y-4">
      <div className="rounded-lg border border-slate-200 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-medium">My event requests</h2>
          <button
            type="button"
            onClick={() => {
              setOutcome(null)
              setEditing({ id: null, status: 'draft', status_permits: ['edit'], values: emptyForm() })
            }}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          >
            New draft
          </button>
        </div>

        {requests.isPending && <p className="mt-2 text-sm">Loading...</p>}
        {requests.isError && (
          <p className="mt-2 text-sm text-red-600" role="alert">
            Could not load your requests: {requests.error.message}
          </p>
        )}
        {requests.data && requests.data.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">You have no event requests yet.</p>
        )}

        {requests.data && requests.data.length > 0 && (
          <ul className="mt-3 divide-y divide-slate-200">
            {requests.data.map((request) => (
              <li
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-4 py-3"
              >
                <div>
                  <p className="font-medium">{titleOf(request)}</p>
                  <p className="text-sm text-slate-500">
                    <StatusLabel status={request.status} />
                  </p>
                </div>
                {request.status_permits.includes('edit') ? (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => reopen.mutate(request.id)}
                      disabled={reopen.isPending}
                      aria-label={`Edit draft ${titleOf(request)}`}
                      className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                    >
                      Edit draft
                    </button>
                    {request.status_permits.includes('submit') && (
                      <button
                        type="button"
                        onClick={() => submit.mutate(request)}
                        disabled={submit.isPending}
                        className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                      >
                        Submit for review
                      </button>
                    )}
                  </div>
                ) : (
                  <span className="text-sm text-slate-500">
                    Locked - ask your coordinator to request changes
                  </span>
                )}
                {request.status === 'submitted' && (
                  <div className="basis-full">
                    <ClarificationThread eventRequestId={request.id} mode="organiser" />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <DraftForm
          state={editing}
          onChange={setEditing}
          onCancel={() => setEditing(null)}
          onSave={() => saveDraft.mutate(editing)}
          onSubmit={() =>
            editing.id && submit.mutate({ id: editing.id, name: nullableText(editing.values.name) })
          }
          isSaving={saveDraft.isPending}
          isSubmitting={submit.isPending}
        />
      )}

      <section className="rounded-lg border border-slate-200 p-4">
        <h2 className="font-medium">Organisation drafts</h2>
        {visibleDrafts.isPending && <p className="mt-2 text-sm">Loading...</p>}
        {visibleDrafts.isError && (
          <p className="mt-2 text-sm text-red-600" role="alert">
            Could not load organisation drafts: {visibleDrafts.error.message}
          </p>
        )}
        {visibleDrafts.data && visibleDrafts.data.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">No organisation drafts are visible.</p>
        )}
        {visibleDrafts.data && visibleDrafts.data.length > 0 && (
          <ul className="mt-3 divide-y divide-slate-200">
            {visibleDrafts.data.map((request) => (
              <li
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-4 py-3"
              >
                <div>
                  <p className="font-medium">{titleOf(request)}</p>
                  <p className="text-sm text-slate-500">
                    <StatusLabel status={request.status} />
                    {ownIds.has(request.id) ? ' - Your draft' : ' - Shared draft'}
                  </p>
                </div>
                {!ownIds.has(request.id) && (
                  <span className="text-sm text-slate-500">Read-only</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {outcome && <OutcomeMessage outcome={outcome} />}
    </section>
  )
}

type Outcome =
  | { kind: 'incomplete'; name: string | null; problems: FieldProblem[] }
  | { kind: 'saved'; request: EventRequest }
  | { kind: 'submitted'; request: EventRequest }
  | { kind: 'failed'; message: string }

interface EditingState {
  id: string | null
  status: EventRequest['status']
  status_permits: EventRequest['status_permits']
  values: DraftFormValues
}

interface DraftFormValues {
  name: string
  purpose: string
  description: string
  start_at: string
  end_at: string
  expected_attendance: string
  venue_requirement: string
  accessibility_requirement: string
  equipment_requirement: string
  layout_requirement: string
  registration_requirement: string
}

type SubmitTarget = Pick<EventRequest, 'id' | 'name'>

function StatusLabel({ status }: { status: EventRequest['status'] }) {
  if (status === 'submitted') return <>Submitted</>
  if (status === 'approved') return <>Approved</>
  if (status === 'rejected') return <>Rejected</>
  return <>Draft</>
}

function OutcomeMessage({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === 'saved') {
    return (
      <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-800">
        “{titleOf(outcome.request)}” was saved as a Draft.
      </p>
    )
  }
  if (outcome.kind === 'submitted') {
    return (
      <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-800">
        “{titleOf(outcome.request)}” has been submitted for review. Its status is now Submitted.
      </p>
    )
  }
  if (outcome.kind === 'incomplete') {
    return (
      <div role="alert" className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-900">
        <p>“{outcome.name ?? 'This request'}” cannot be submitted yet. Please correct:</p>
        <ul className="mt-2 list-disc pl-5">
          {outcome.problems.map((problem) => (
            <li key={problem.field}>
              {FIELD_LABELS[problem.field] ?? problem.field} {problem.reason}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
      {outcome.message}
    </p>
  )
}

function DraftForm({
  state,
  onChange,
  onCancel,
  onSave,
  onSubmit,
  isSaving,
  isSubmitting,
}: {
  state: EditingState
  onChange: (state: EditingState) => void
  onCancel: () => void
  onSave: () => void
  onSubmit: () => void
  isSaving: boolean
  isSubmitting: boolean
}) {
  const update = (field: keyof DraftFormValues, value: string) => {
    onChange({ ...state, values: { ...state.values, [field]: value } })
  }

  return (
    <form
      aria-label="Event request draft form"
      className="rounded-lg border border-slate-200 p-4"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-medium">{state.id ? 'Edit event request' : 'New event request'}</h2>
          <p className="text-sm text-slate-500">
            Status: <StatusLabel status={state.status} />
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Close
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Field label="Name" value={state.values.name} onChange={(value) => update('name', value)} />
        <Field
          label="Purpose"
          value={state.values.purpose}
          onChange={(value) => update('purpose', value)}
        />
        <Field
          label="Start date and time"
          value={state.values.start_at}
          onChange={(value) => update('start_at', value)}
        />
        <Field
          label="End date and time"
          value={state.values.end_at}
          onChange={(value) => update('end_at', value)}
        />
        <Field
          label="Expected attendance"
          type="number"
          value={state.values.expected_attendance}
          onChange={(value) => update('expected_attendance', value)}
        />
        <Field
          label="Venue requirement"
          value={state.values.venue_requirement}
          onChange={(value) => update('venue_requirement', value)}
        />
        <Field
          label="Accessibility requirement"
          value={state.values.accessibility_requirement}
          onChange={(value) => update('accessibility_requirement', value)}
        />
        <Field
          label="Equipment requirement"
          value={state.values.equipment_requirement}
          onChange={(value) => update('equipment_requirement', value)}
        />
        <Field
          label="Layout requirement"
          value={state.values.layout_requirement}
          onChange={(value) => update('layout_requirement', value)}
        />
        <Field
          label="Registration requirement"
          value={state.values.registration_requirement}
          onChange={(value) => update('registration_requirement', value)}
        />
        <label className="md:col-span-2">
          <span className="text-sm font-medium text-slate-700">Description</span>
          <textarea
            value={state.values.description}
            onChange={(event) => update('description', event.target.value)}
            className="mt-1 min-h-24 w-full rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={isSaving || !state.status_permits.includes('edit')}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Save Draft
        </button>
        {state.id && state.status_permits.includes('submit') && (
          <button
            type="button"
            onClick={onSubmit}
            disabled={isSubmitting}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Submit for review
          </button>
        )}
      </div>
    </form>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: 'text' | 'number'
}) {
  return (
    <label>
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
      />
    </label>
  )
}

function emptyForm(): DraftFormValues {
  return {
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
}

function toForm(request: EventRequest): DraftFormValues {
  return {
    name: request.name ?? '',
    purpose: request.purpose ?? '',
    description: request.description ?? '',
    start_at: request.start_at ?? '',
    end_at: request.end_at ?? '',
    expected_attendance: request.expected_attendance?.toString() ?? '',
    venue_requirement: request.venue_requirement ?? '',
    accessibility_requirement: request.accessibility_requirement ?? '',
    equipment_requirement: request.equipment_requirement ?? '',
    layout_requirement: request.layout_requirement ?? '',
    registration_requirement: request.registration_requirement ?? '',
  }
}

function toDraftPayload(values: DraftFormValues): EventRequestDraftInput {
  return {
    name: nullableText(values.name),
    purpose: nullableText(values.purpose),
    description: nullableText(values.description),
    start_at: nullableText(values.start_at),
    end_at: nullableText(values.end_at),
    expected_attendance:
      values.expected_attendance.trim() === '' ? null : Number(values.expected_attendance),
    venue_requirement: nullableText(values.venue_requirement),
    accessibility_requirement: nullableText(values.accessibility_requirement),
    equipment_requirement: nullableText(values.equipment_requirement),
    layout_requirement: nullableText(values.layout_requirement),
    registration_requirement: nullableText(values.registration_requirement),
  }
}

function nullableText(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function titleOf(request: EventRequest): string {
  return request.name ?? 'Untitled request'
}

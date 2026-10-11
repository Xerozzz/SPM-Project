import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import {
  createDraft,
  EventRequestValidationError,
  type FieldProblem,
  submitEventRequest,
  updateDraft,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import {
  emptyEventRequestForm,
  type EventRequestFieldErrors,
  type EventRequestFieldName,
  type EventRequestFormValues,
  eventRequestToDraftInput,
  eventRequestToFormValues,
  validateEventRequest,
} from '../validation/eventRequest'
import EventRequestFields from './EventRequestFields'

interface DraftAction {
  id: string | null
  values: EventRequestFormValues
}

/** SCRUM-28/SCRUM-29: one creation form saves incomplete drafts or submits complete ones. */
export default function EventRequestForm() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [draftId, setDraftId] = useState<string | null>(null)
  const [values, setValues] = useState<EventRequestFormValues>(emptyEventRequestForm)
  const [errors, setErrors] = useState<EventRequestFieldErrors>({})
  const [outcome, setOutcome] = useState<string | null>(null)

  const refreshLists = () => {
    void queryClient.invalidateQueries({ queryKey: ['event-requests', 'mine', token] })
    void queryClient.invalidateQueries({ queryKey: ['event-requests', 'drafts', token] })
    void queryClient.invalidateQueries({ queryKey: ['organisation-calendar', token] })
  }

  const saveDraft = useMutation({
    mutationFn: ({ id, values: submittedValues }: DraftAction) => {
      const payload = eventRequestToDraftInput(submittedValues)
      return id === null ? createDraft(token ?? '', payload) : updateDraft(token ?? '', id, payload)
    },
    onSuccess: (request) => {
      setDraftId(request.id)
      setValues(eventRequestToFormValues(request))
      setErrors({})
      setOutcome(`“${request.name ?? 'Untitled request'}” was saved as a draft.`)
      refreshLists()
    },
    onError: showServerErrors,
  })

  const submitRequest = useMutation({
    mutationFn: async ({ id, values: submittedValues }: DraftAction) => {
      const payload = eventRequestToDraftInput(submittedValues)
      const draft =
        id === null
          ? await createDraft(token ?? '', payload)
          : await updateDraft(token ?? '', id, payload)
      return submitEventRequest(token ?? '', draft.id)
    },
    onSuccess: (request) => {
      setDraftId(null)
      setValues(emptyEventRequestForm())
      setErrors({})
      setOutcome(
        `“${request.name ?? 'Untitled request'}” has been submitted for review and is now read-only.`,
      )
      refreshLists()
    },
    onError: showServerErrors,
  })

  function showServerErrors(error: Error) {
    if (error instanceof EventRequestValidationError) {
      setErrors(problemsToErrors(error.problems))
    }
    setOutcome(error.message)
  }

  function change(name: EventRequestFieldName, value: string) {
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: undefined }))
    setOutcome(null)
  }

  function save() {
    setErrors({})
    setOutcome(null)
    saveDraft.mutate({ id: draftId, values })
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOutcome(null)
    const validationErrors = validateEventRequest(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length === 0) {
      submitRequest.mutate({ id: draftId, values })
    }
  }

  const pending = saveDraft.isPending || submitRequest.isPending
  const failed = saveDraft.isError || submitRequest.isError

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">{draftId ? 'Edit saved draft' : 'New event request'}</h2>
      <p className="mt-1 text-sm text-slate-500">
        Fields marked * are required to submit. A draft may be incomplete.
      </p>
      <form className="mt-4 space-y-4" noValidate onSubmit={submit}>
        <EventRequestFields
          idPrefix="new-event"
          values={values}
          errors={errors}
          onChange={change}
        />
        {draftId && (
          <p className="text-sm text-slate-500">
            This saved draft remains open so you can continue editing it.
          </p>
        )}
        {failed && outcome && (
          <p role="alert" className="text-sm text-red-600">
            {outcome}. Your entered details are still available to edit.
          </p>
        )}
        {!failed && outcome && (
          <p role="status" className="text-sm text-green-700">
            {outcome}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={save}
            disabled={pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Save draft
          </button>
          <button
            type="submit"
            disabled={pending}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Submit for review
          </button>
        </div>
      </form>
    </section>
  )
}

function problemsToErrors(problems: FieldProblem[]): EventRequestFieldErrors {
  return Object.fromEntries(problems.map((problem) => [problem.field, problem.reason]))
}

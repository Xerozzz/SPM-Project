import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import type { EventRequest } from '../api/eventRequests'
import {
  closeRegistration,
  extendRegistration,
  openRegistration,
  readRegistrationSettings,
} from '../api/registrationIntake'
import { useAuth } from '../auth/useAuth'

/** SCRUM-113: the owner's minimal open/extend control; eligibility remains server-side. */
export default function RegistrationIntakeControls({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [deadline, setDeadline] = useState('')
  const key = ['registration-settings', event.id, token]
  const settings = useQuery({
    queryKey: key,
    queryFn: () => readRegistrationSettings(token ?? '', event.id),
    enabled: token !== null,
  })
  const update = useMutation({
    mutationFn: (action: 'open' | 'extend') =>
      action === 'open'
        ? openRegistration(token ?? '', event.id, deadline || null)
        : extendRegistration(token ?? '', event.id, deadline),
    onSuccess: () => void client.invalidateQueries({ queryKey: key }),
  })
  const close = useMutation({
    mutationFn: () => closeRegistration(token ?? '', event.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: key }),
  })

  if (!settings.data?.registration_enabled) return null
  const isOpen = settings.data.intake_open
  const manuallyClosed = settings.data.closed_at !== null
  return (
    <section className="mt-3 rounded border border-slate-200 p-3">
      <h3 className="text-sm font-medium">Registration</h3>
      <p className="mt-1 text-sm text-slate-500">
        {isOpen
          ? settings.data.closes_at
            ? `Open until ${new Date(settings.data.closes_at).toLocaleString()}.`
            : 'Open with no closing deadline.'
          : settings.data.closed_at
            ? `Closed at ${new Date(settings.data.closed_at).toLocaleString()}.`
            : 'Not open for attendee intake.'}
      </p>
      {!manuallyClosed && (
        <>
          <label className="mt-2 block text-sm" htmlFor={`registration-deadline-${event.id}`}>
            Closing deadline (optional when opening)
          </label>
          <input
            id={`registration-deadline-${event.id}`}
            type="datetime-local"
            value={deadline}
            onChange={(change) => setDeadline(change.target.value)}
            className="mt-1 rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            disabled={update.isPending || (isOpen && !deadline)}
            onClick={() => update.mutate(isOpen ? 'extend' : 'open')}
            className="ml-2 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {isOpen ? 'Extend deadline' : 'Open registration'}
          </button>
        </>
      )}
      {isOpen && (
        <button
          type="button"
          disabled={close.isPending}
          onClick={() => close.mutate()}
          className="ml-2 rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
        >
          Close registration
        </button>
      )}
      {update.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {update.error.message}
        </p>
      )}
      {close.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {close.error.message}
        </p>
      )}
    </section>
  )
}

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import type { EventRequest } from '../api/eventRequests'
import { readRegistrationSettings } from '../api/registrationIntake'
import { useAuth } from '../auth/useAuth'

/** SCRUM-113: the assigned Coordinator may inspect intake, but never control it. */
export default function RegistrationSettingsCard({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const client = useQueryClient()
  const settings = useQuery({
    queryKey: ['registration-settings', event.id, token],
    queryFn: () => readRegistrationSettings(token ?? '', event.id),
    enabled: token !== null,
  })
  const closingDeadline = settings.data?.closes_at
  const deadlineExpired = settings.data?.deadline_expired

  useEffect(() => {
    if (!closingDeadline || deadlineExpired) return
    const milliseconds = new Date(closingDeadline).getTime() - Date.now()
    if (milliseconds <= 0) return
    const timer = window.setTimeout(
      () =>
        void client.invalidateQueries({
          queryKey: ['registration-settings', event.id, token],
        }),
      milliseconds,
    )
    return () => window.clearTimeout(timer)
  }, [client, closingDeadline, deadlineExpired, event.id, token])

  if (settings.isPending)
    return <p className="mt-3 text-sm text-slate-500">Loading registration…</p>
  if (settings.isError) {
    return <p className="mt-3 text-sm text-red-600">Could not load registration settings.</p>
  }
  if (!settings.data?.registration_enabled) return null

  const { data } = settings
  return (
    <section
      className="mt-3 rounded border border-slate-200 p-3"
      aria-label="Registration settings"
    >
      <h4 className="text-sm font-medium">Registration</h4>
      <p className="mt-1 text-sm text-slate-500">
        {data.intake_open
          ? data.closes_at
            ? `Open until ${new Date(data.closes_at).toLocaleString()}.`
            : 'Open with no closing deadline.'
          : data.closed_at
            ? `Closed manually at ${new Date(data.closed_at).toLocaleString()}.`
            : data.deadline_expired
              ? `Closed automatically at ${new Date(data.closes_at ?? '').toLocaleString()}.`
              : 'Not open for attendee intake.'}
      </p>
      <dl className="mt-2 text-sm text-slate-600">
        <div>
          <dt className="inline font-medium">Opened: </dt>
          <dd className="inline">
            {data.opened_at ? new Date(data.opened_at).toLocaleString() : 'Not opened'}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">Closing deadline: </dt>
          <dd className="inline">
            {data.closes_at ? new Date(data.closes_at).toLocaleString() : 'No deadline'}
          </dd>
        </div>
      </dl>
    </section>
  )
}

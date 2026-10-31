import { useMutation, useQueryClient } from '@tanstack/react-query'

import { markNotificationViewed } from '../api/notifications'
import { formatDisplayTime } from '../presentation/dates'
import { useAuth } from '../auth/useAuth'
import { useNotificationInbox } from '../hooks/useNotificationInbox'
import { NOTIFICATION_TITLES, notificationLink } from '../presentation/notifications'

/** SCRUM-99: readable private updates, with source identifiers available on demand. */
export default function NotificationInbox({
  allowedViews,
  onNavigate,
}: {
  allowedViews?: string[]
  onNavigate?: (view: string, eventId?: string | null, bookingId?: string | null) => void
} = {}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const inbox = useNotificationInbox()
  const markViewed = useMutation({
    mutationFn: (id: string) => markNotificationViewed(token ?? '', id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['notifications', 'inbox', token] }),
  })
  return (
    <section aria-label="Notifications">
      {inbox.isPending && <p className="mt-2 text-sm">Loading notifications…</p>}
      {inbox.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load notifications: {inbox.error.message}
        </p>
      )}
      {inbox.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">
          You have no notifications. New activity on your events will appear here.
        </p>
      )}
      {inbox.data && inbox.data.length > 0 && (
        <ul className="space-y-3">
          {inbox.data.map((notification) => {
            const link = notificationLink(notification, allowedViews)
            return (
              <li
                key={notification.id}
                className={`rounded-xl border p-5 text-sm ${notification.is_unread ? 'border-sky-200 bg-sky-50/40' : 'border-slate-200 bg-white'}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="!text-base !leading-6 font-semibold tracking-normal">
                    {NOTIFICATION_TITLES[notification.type] ?? 'Event update'}
                  </h2>
                  {notification.is_unread && (
                    <span className="rounded-full bg-sky-100 px-2 py-1 text-xs font-medium text-sky-800">
                      Unread
                    </span>
                  )}
                </div>
                <p className="mt-2 font-medium text-slate-800">
                  {notification.event_name || 'Untitled event'}
                </p>
                <time dateTime={notification.occurred_at} className="mt-1 block text-slate-500">
                  {formatDisplayTime(notification.occurred_at)}
                </time>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  {link && (
                    <a
                      href={link.href}
                      className="font-medium text-sky-800 underline underline-offset-4"
                      onClick={(event) => {
                        if (
                          onNavigate &&
                          !event.metaKey &&
                          !event.ctrlKey &&
                          !event.shiftKey &&
                          !event.altKey
                        ) {
                          event.preventDefault()
                          onNavigate(link.view, link.eventId, link.bookingId)
                        }
                      }}
                    >
                      {link.label}
                    </a>
                  )}
                  {notification.is_unread && (
                    <button
                      type="button"
                      disabled={markViewed.isPending}
                      onClick={() => markViewed.mutate(notification.id)}
                      className="cs-button-secondary"
                    >
                      Mark viewed
                    </button>
                  )}
                </div>
                <details className="mt-4 text-xs text-slate-500">
                  <summary className="cursor-pointer">Record details</summary>
                  <dl className="mt-2 space-y-1 break-words">
                    <div>
                      <dt className="inline">Event ID: </dt>
                      <dd className="inline">{notification.event_request_id}</dd>
                    </div>
                    <div>
                      <dt className="inline">Action: </dt>
                      <dd className="inline">
                        {notification.type} · {notification.source_type} {notification.source_id}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline">Occurred: </dt>
                      <dd className="inline">{notification.occurred_at}</dd>
                    </div>
                    {notification.viewed_at && (
                      <div>
                        <dt className="inline">Viewed: </dt>
                        <dd className="inline">{notification.viewed_at}</dd>
                      </div>
                    )}
                  </dl>
                </details>
              </li>
            )
          })}
        </ul>
      )}
      {markViewed.isError && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {markViewed.error.message}
        </p>
      )}
    </section>
  )
}

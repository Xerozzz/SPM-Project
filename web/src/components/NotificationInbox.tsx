import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { listNotifications, markNotificationViewed } from '../api/notifications'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-99: the signed-in user's private notification inbox. Every entry shows its
 * related event, the triggering action, and when it happened, newest first. Unread
 * entries carry both a badge and the word "Unread" (never colour alone); marking
 * viewed keeps the row visible with its viewed time.
 */
export default function NotificationInbox() {
  const { token } = useAuth()
  const client = useQueryClient()
  const inboxKey = ['notifications', 'inbox', token]
  const inbox = useQuery({
    queryKey: inboxKey,
    queryFn: () => listNotifications(token ?? ''),
    enabled: token !== null,
  })
  const markViewed = useMutation({
    mutationFn: (id: string) => markNotificationViewed(token ?? '', id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: inboxKey })
    },
  })

  return (
    <section aria-label="Notifications" className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Notifications</h2>
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
        <ul className="mt-2 space-y-3">
          {inbox.data.map((notification) => (
            <li
              key={notification.id}
              className="rounded border border-slate-200 p-3 text-sm"
              aria-label={`${notification.is_unread ? 'Unread' : 'Viewed'} notification for event ${notification.event_request_id}`}
            >
              <p className="font-medium">
                {notification.is_unread && (
                  <span className="mr-2 rounded bg-blue-600 px-1.5 py-0.5 text-xs font-semibold text-white">
                    Unread
                  </span>
                )}
                {notification.type}
              </p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600">
                <dt className="font-medium text-slate-500">Event ID</dt>
                <dd>{notification.event_request_id}</dd>
                <dt className="font-medium text-slate-500">Action</dt>
                <dd>
                  {notification.source_type} {notification.source_id}
                </dd>
                <dt className="font-medium text-slate-500">Happened</dt>
                <dd>{notification.occurred_at}</dd>
                {!notification.is_unread && (
                  <>
                    <dt className="font-medium text-slate-500">Viewed</dt>
                    <dd>{notification.viewed_at}</dd>
                  </>
                )}
              </dl>
              {notification.is_unread && (
                <button
                  type="button"
                  disabled={markViewed.isPending}
                  onClick={() => markViewed.mutate(notification.id)}
                  className="mt-2 rounded border border-slate-300 px-2 py-1"
                >
                  Mark viewed
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

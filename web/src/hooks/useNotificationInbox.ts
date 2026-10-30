import { useQuery } from '@tanstack/react-query'

import { listNotifications } from '../api/notifications'
import { useAuth } from '../auth/useAuth'

/** SCRUM-99: the sidebar and inbox share the same recipient-specific query. */
export function useNotificationInbox() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['notifications', 'inbox', token],
    queryFn: () => listNotifications(token ?? ''),
    enabled: token !== null,
  })
}

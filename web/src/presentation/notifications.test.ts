import { expect, test } from 'vitest'

import type { Notification } from '../api/notifications'
import { notificationLink } from './notifications'

// SCRUM-99 / SCRUM-102: shared updates lead each recipient to a permitted workspace.
const notification: Notification = {
  id: 'notification-1',
  event_request_id: 'event-1',
  event_name: 'Welcome Fair',
  type: 'coordinator_assigned',
  source_type: 'coordinator_assignment',
  source_id: 'assignment-1',
  occurred_at: '2026-10-30T10:00:00Z',
  created_at: '2026-10-30T10:00:00Z',
  viewed_at: null,
  is_unread: true,
}

test('assignment recipients reach their own role workspace', () => {
  expect(notificationLink(notification, ['my-events', 'notifications'])?.href).toBe(
    '?view=my-events&event=event-1',
  )
  expect(notificationLink(notification, ['review-queue', 'notifications'])?.href).toBe(
    '?view=review-queue&event=event-1',
  )
})

test('a safety decision also opens the owning organiser event', () => {
  const decision = { ...notification, type: 'safety_approved', source_type: 'safety_review' }
  expect(notificationLink(decision, ['my-events', 'notifications'])?.view).toBe('my-events')
})

test('a link is omitted when no destination is permitted for the role', () => {
  expect(notificationLink(notification, ['registrations', 'notifications'])).toBeNull()
})

// SCRUM-88 / SCRUM-115: terminal events leave the coordinator's working queue.
test('cancellation links lead coordinators to retained records and organisers to their event', () => {
  const cancelled = { ...notification, type: 'event_cancelled', source_type: 'event_cancellation' }
  expect(notificationLink(cancelled, ['review-queue', 'notifications'])?.view).toBe('review-queue')
  expect(notificationLink(cancelled, ['active-assignments', 'notifications'])?.view).toBe(
    'active-assignments',
  )
  expect(notificationLink(cancelled, ['my-events', 'notifications'])?.view).toBe('my-events')
})

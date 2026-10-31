import type { Notification } from '../api/notifications'

// SCRUM-99: presentation copy; stored notification identities remain unchanged.
export const NOTIFICATION_TITLES: Record<string, string> = {
  general: 'Event update',
  request_approved: 'Event request approved',
  request_rejected: 'Event request rejected',
  coordinator_assigned: 'Coordinator assigned',
  coordinator_reassigned: 'Coordinator reassigned',
  unassigned_submission: 'New event awaiting assignment',
  venue_hold_expired: 'Venue hold expired',
  venue_closure_impact: 'Venue closure affects an arrangement',
  venue_request_submitted: 'New venue request awaiting review',
  venue_booking_approved: 'Venue placed on tentative hold',
  venue_booking_rejected: 'Venue request rejected',
  venue_hold_expiry_updated: 'Venue hold expiry updated',
  venue_arrangement_cancelled: 'Venue arrangement cancelled',
  venue_revision_submitted: 'Revised venue request awaiting review',
  equipment_review_needed: 'Equipment requirements need review',
  equipment_review_available: 'Requested equipment is available',
  equipment_review_partially_available: 'Some requested equipment is available',
  equipment_review_unavailable: 'Requested equipment is unavailable',
  equipment_reserved_full: 'Equipment fully reserved',
  equipment_reserved_partial: 'Equipment partially reserved',
  safety_approved: 'Safety review approved',
  safety_rejected: 'Safety review rejected',
  safety_changes_requested: 'Safety review requires changes',
  safety_review_due: 'Event plan ready for safety review',
  change_proposed: 'Event changes proposed',
  change_approved: 'Event changes approved',
  change_rejected: 'Event changes rejected',
  event_confirmed: 'Event confirmed',
  event_replanned: 'Event returned to planning',
  event_completed: 'Event completed',
  event_cancelled: 'Event cancelled',
  cancellation_requested: 'Event cancellation requested',
  cancellation_declined: 'Cancellation request declined',
  registration_pending: 'Registration awaiting a decision',
  registration_accepted: 'Registration accepted',
  registration_waitlisted: 'Registration added to the waiting list',
  registration_withdrawn: 'Registration withdrawn',
  arrangements_incomplete: 'Event arrangements need attention',
}

type NotificationDestination = {
  views: string[]
  label: string
  /** Most notifications open their parent event; venue records need their own booking ID. */
  target: 'event' | 'booking'
}

const DESTINATIONS: Record<string, NotificationDestination> = {
  coordinator_assignment: {
    views: ['review-queue', 'my-events'],
    label: 'View assigned event',
    target: 'event',
  },
  event_decision: { views: ['my-events'], label: 'View event', target: 'event' },
  venue_booking: { views: ['review-queue'], label: 'View venue arrangement', target: 'event' },
  venue_closure: { views: ['review-queue'], label: 'Review affected arrangement', target: 'event' },
  event_reminder: { views: ['review-queue'], label: 'Review event arrangements', target: 'event' },
  safety_review: {
    views: ['review-queue', 'my-events'],
    label: 'View safety decision',
    target: 'event',
  },
  change_request: { views: ['review-queue'], label: 'Review proposed changes', target: 'event' },
  change_decision: { views: ['my-events'], label: 'View change decision', target: 'event' },
  cancellation_request: {
    views: ['review-queue'],
    label: 'Review cancellation request',
    target: 'event',
  },
  cancellation_decision: {
    views: ['my-events'],
    label: 'View cancellation decision',
    target: 'event',
  },
  registration_status: {
    views: ['registrations'],
    label: 'View my registration status',
    target: 'event',
  },
  equipment_requirement_change: {
    views: ['equipment-review'],
    label: 'Review equipment requirements',
    target: 'event',
  },
  equipment_review: { views: ['review-queue'], label: 'View equipment outcome', target: 'event' },
  equipment_reservation: {
    views: ['review-queue'],
    label: 'View equipment outcome',
    target: 'event',
  },
  venue_decision: { views: ['review-queue'], label: 'View venue decision', target: 'event' },
  venue_cancellation: {
    views: ['booking-decisions'],
    label: 'View venue booking decisions',
    target: 'booking',
  },
  venue_request: { views: ['booking-decisions'], label: 'Review venue request', target: 'booking' },
  venue_revision: {
    views: ['booking-decisions'],
    label: 'Review revised venue request',
    target: 'booking',
  },
  event_submission: {
    views: ['unassigned-queue'],
    label: 'Review event assignment',
    target: 'event',
  },
  safety_plan: { views: ['safety-review'], label: 'Review event safety', target: 'event' },
  event_completion: {
    views: ['completed-events', 'my-events'],
    label: 'View completed event',
    target: 'event',
  },
  event_cancellation: {
    views: ['review-queue', 'active-assignments', 'my-events', 'registrations'],
    label: 'View cancelled event',
    target: 'event',
  },
}

export function notificationLink(notification: Notification, allowedViews?: string[]) {
  const target = DESTINATIONS[notification.source_type] ?? {
    views: ['my-events', 'review-queue', 'active-assignments', 'registrations'],
    label: 'View event',
    target: 'event' as const,
  }
  const view = target.views.find((id) => !allowedViews || allowedViews.includes(id))
  return view
    ? {
        view,
        label: target.label,
        href: `?${new URLSearchParams(
          target.target === 'booking'
            ? { view, booking: notification.source_id }
            : { view, event: notification.event_request_id },
        )}`,
        eventId: target.target === 'event' ? notification.event_request_id : null,
        bookingId: target.target === 'booking' ? notification.source_id : null,
      }
    : null
}

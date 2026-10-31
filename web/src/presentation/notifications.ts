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

const DESTINATIONS: Record<string, { views: string[]; label: string }> = {
  coordinator_assignment: { views: ['review-queue', 'my-events'], label: 'View assigned event' },
  event_decision: { views: ['my-events'], label: 'View event' },
  venue_booking: { views: ['review-queue'], label: 'View venue arrangement' },
  venue_closure: { views: ['review-queue'], label: 'Review affected arrangement' },
  event_reminder: { views: ['review-queue'], label: 'Review event arrangements' },
  safety_review: { views: ['review-queue', 'my-events'], label: 'View safety decision' },
  change_request: { views: ['review-queue'], label: 'Review proposed changes' },
  change_decision: { views: ['my-events'], label: 'View change decision' },
  cancellation_request: { views: ['review-queue'], label: 'Review cancellation request' },
  cancellation_decision: { views: ['my-events'], label: 'View cancellation decision' },
  registration_status: { views: ['registrations'], label: 'View my registration status' },
  equipment_requirement_change: {
    views: ['equipment-review'],
    label: 'Review equipment requirements',
  },
  equipment_review: { views: ['review-queue'], label: 'View equipment outcome' },
  equipment_reservation: { views: ['review-queue'], label: 'View equipment outcome' },
  venue_decision: { views: ['review-queue'], label: 'View venue decision' },
  venue_cancellation: { views: ['booking-decisions'], label: 'View venue booking decisions' },
  venue_request: { views: ['booking-decisions'], label: 'Review venue request' },
  venue_revision: { views: ['booking-decisions'], label: 'Review revised venue request' },
  event_submission: { views: ['unassigned-queue'], label: 'Review event assignment' },
  safety_plan: { views: ['safety-review'], label: 'Review event safety' },
  event_completion: { views: ['completed-events', 'my-events'], label: 'View completed event' },
  event_cancellation: {
    views: ['review-queue', 'active-assignments', 'my-events', 'registrations'],
    label: 'View cancelled event',
  },
}

export function notificationLink(notification: Notification, allowedViews?: string[]) {
  const target = DESTINATIONS[notification.source_type] ?? {
    views: ['my-events', 'review-queue', 'active-assignments', 'registrations'],
    label: 'View event',
  }
  const view = target.views.find((id) => !allowedViews || allowedViews.includes(id))
  return view
    ? {
        view,
        label: target.label,
        href: `?${new URLSearchParams({ view, event: notification.event_request_id })}`,
      }
    : null
}

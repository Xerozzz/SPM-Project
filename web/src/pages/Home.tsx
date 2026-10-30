import { useState } from 'react'

import type { EventRequest } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import { useNotificationInbox } from '../hooks/useNotificationInbox'
import { useWorkspaceNavigation } from '../hooks/useWorkspaceNavigation'
import AppShell, { type NavigationItem } from '../components/AppShell'
import ActiveAssignments from '../components/ActiveAssignments'
import AttendeeRegistrations from '../components/AttendeeRegistrations'
import BookingProblems from '../components/BookingProblems'
import CompletedEvents from '../components/CompletedEvents'
import EquipmentCatalogue from '../components/EquipmentCatalogue'
import EquipmentReviewQueue from '../components/EquipmentReviewQueue'
import EventRequestForm from '../components/EventRequestForm'
import EventRequestReview from '../components/EventRequestReview'
import MyEventRequests from '../components/MyEventRequests'
import NotificationInbox from '../components/NotificationInbox'
import OrganisationEventCalendar from '../components/OrganisationEventCalendar'
import SafetyReviewQueue from '../components/SafetyReviewQueue'
import UnassignedQueue from '../components/UnassignedQueue'
import VenueBookingDecisions from '../components/VenueBookingDecisions'
import VenueCalendar from '../components/VenueCalendar'
import VenueCatalogue from '../components/VenueCatalogue'
import VenueSearch from '../components/VenueSearch'

type View =
  | 'my-events'
  | 'event-calendar'
  | 'registrations'
  | 'review-queue'
  | 'completed-events'
  | 'venue-planning'
  | 'unassigned-queue'
  | 'active-assignments'
  | 'venue-catalogue'
  | 'booking-decisions'
  | 'booking-problems'
  | 'venue-calendar'
  | 'equipment-catalogue'
  | 'equipment-review'
  | 'safety-review'
  | 'notifications'

const VIEW_DETAILS: Record<View, Omit<NavigationItem, 'group' | 'icon'>> = {
  'my-events': {
    id: 'my-events',
    label: 'My Events',
    description: 'Create, manage, and follow your event requests.',
  },
  'event-calendar': {
    id: 'event-calendar',
    label: 'Event Calendar',
    description: 'Your organisation’s event schedule.',
  },
  registrations: {
    id: 'registrations',
    label: 'Event Registrations',
    description: 'Browse open events and manage your registrations.',
  },
  'review-queue': {
    id: 'review-queue',
    label: 'Review Queue',
    description: 'Review and progress your assigned event plans.',
  },
  'completed-events': {
    id: 'completed-events',
    label: 'Completed Events',
    description: 'Review completed events and closure notes.',
  },
  'venue-planning': {
    id: 'venue-planning',
    label: 'Venue Planning',
    description: 'Search venues, plan arrangements, and view availability.',
  },
  'unassigned-queue': {
    id: 'unassigned-queue',
    label: 'Unassigned Queue',
    description: 'Assign coordinators to newly submitted events.',
  },
  'active-assignments': {
    id: 'active-assignments',
    label: 'Active Assignments',
    description: 'Review event ownership and reassign work when needed.',
  },
  'venue-catalogue': {
    id: 'venue-catalogue',
    label: 'Venue Catalogue',
    description: 'Maintain venue details and availability.',
  },
  'booking-decisions': {
    id: 'booking-decisions',
    label: 'Booking Decisions',
    description: 'Review, hold, approve, or reject venue bookings.',
  },
  'booking-problems': {
    id: 'booking-problems',
    label: 'Booking Conflicts',
    description: 'Review bookings and tentative holds affected by venue changes.',
  },
  'venue-calendar': {
    id: 'venue-calendar',
    label: 'Venue Calendar',
    description: 'See venue bookings, holds, and availability.',
  },
  'equipment-catalogue': {
    id: 'equipment-catalogue',
    label: 'Equipment Catalogue',
    description: 'Maintain the available equipment catalogue.',
  },
  'equipment-review': {
    id: 'equipment-review',
    label: 'Equipment Review Queue',
    description: 'Review requirements and record equipment reservations.',
  },
  'safety-review': {
    id: 'safety-review',
    label: 'Safety Review Queue',
    description: 'Assess active event plans and record safety decisions.',
  },
  notifications: {
    id: 'notifications',
    label: 'Notifications',
    description: 'Read your event and workflow updates.',
  },
}

/** The authenticated workspace. Views stay mounted while hidden to preserve workflow state. */
export default function HomePage() {
  const { roles, signOut, hasRole } = useAuth()
  const [editingDraft, setEditingDraft] = useState<EventRequest | null>(null)
  const [showEventForm, setShowEventForm] = useState(false)
  const [eventNotice, setEventNotice] = useState<string | null>(null)
  const [eventFormDirty, setEventFormDirty] = useState(false)
  const [venueFormDirty, setVenueFormDirty] = useState(false)
  const [venueVersion, setVenueVersion] = useState(0)
  const inbox = useNotificationInbox()
  const items: NavigationItem[] = [
    ...(hasRole('organiser')
      ? [nav('my-events', 'Organise', '◫'), nav('event-calendar', 'Organise', '◷')]
      : []),
    ...(hasRole('attendee') ? [nav('registrations', 'Attend', '✓')] : []),
    ...(hasRole('coordinator')
      ? [
          nav('review-queue', 'Coordinate', '⌁'),
          nav('completed-events', 'Coordinate', '✓'),
          nav('venue-planning', 'Coordinate', '⌂'),
        ]
      : []),
    ...(hasRole('coordinator_lead')
      ? [nav('unassigned-queue', 'Lead', '↗'), nav('active-assignments', 'Lead', '⇄')]
      : []),
    ...(hasRole('venue_staff')
      ? [
          nav('booking-decisions', 'Venues', '□'),
          nav('venue-catalogue', 'Venues', '⌂'),
          nav('booking-problems', 'Venues', '!'),
          nav('venue-calendar', 'Venues', '◷'),
        ]
      : []),
    ...(hasRole('tech_support')
      ? [nav('equipment-catalogue', 'Equipment', '▣'), nav('equipment-review', 'Equipment', '✓')]
      : []),
    ...(hasRole('safety_officer') ? [nav('safety-review', 'Safety', '⌁')] : []),
    nav('notifications', 'Shared', '●'),
  ]
  function canLeave() {
    if ((eventFormDirty || venueFormDirty) && !window.confirm('Discard your unsaved changes?'))
      return false
    if (eventFormDirty) {
      setShowEventForm(false)
      setEditingDraft(null)
      setEventFormDirty(false)
    }
    if (venueFormDirty) {
      setVenueVersion((version) => version + 1)
      setVenueFormDirty(false)
    }
    return true
  }
  const navigation = useWorkspaceNavigation(
    items.map((item) => item.id),
    canLeave,
  )
  const activeView = navigation.view as View
  const unreadCount = inbox.data?.filter((notification) => notification.is_unread).length ?? 0

  return (
    <AppShell
      activeId={activeView}
      items={items}
      onNavigate={navigation.navigate}
      onSignOut={() => {
        if (canLeave()) signOut()
      }}
      unreadCount={unreadCount}
      roles={roles}
    >
      {hasRole('organiser') && (
        <ViewPanel active={activeView === 'my-events'} labelledBy="my-events-panel">
          {eventNotice && (
            <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
              {eventNotice}
            </p>
          )}
          <div hidden={showEventForm}>
            <MyEventRequests
              targetEventId={activeView === 'my-events' ? navigation.eventId : null}
              onCreateEvent={() => {
                setEditingDraft(null)
                setEventNotice(null)
                setShowEventForm(true)
              }}
              onEditDraft={(request) => {
                setEditingDraft(request)
                setEventNotice(null)
                setShowEventForm(true)
              }}
            />
          </div>
          {showEventForm && (
            <div>
              <button
                type="button"
                className="cs-button-secondary"
                onClick={() => {
                  if (canLeave()) setShowEventForm(false)
                }}
              >
                ← Back to My Events
              </button>
              <EventRequestForm
                editing={editingDraft}
                onDirtyChange={setEventFormDirty}
                onDone={(message) => {
                  if (!message && !canLeave()) return
                  setEventFormDirty(false)
                  setEventNotice(message ?? null)
                  setEditingDraft(null)
                  setShowEventForm(false)
                }}
              />
            </div>
          )}
        </ViewPanel>
      )}
      {hasRole('organiser') && (
        <ViewPanel active={activeView === 'event-calendar'}>
          <OrganisationEventCalendar />
        </ViewPanel>
      )}
      {hasRole('attendee') && (
        <ViewPanel active={activeView === 'registrations'}>
          <AttendeeRegistrations
            targetEventId={activeView === 'registrations' ? navigation.eventId : null}
          />
        </ViewPanel>
      )}
      {hasRole('coordinator') && (
        <ViewPanel active={activeView === 'review-queue'}>
          <EventRequestReview
            targetEventId={activeView === 'review-queue' ? navigation.eventId : null}
          />
        </ViewPanel>
      )}
      {hasRole('coordinator') && (
        <ViewPanel active={activeView === 'completed-events'}>
          <CompletedEvents
            targetEventId={activeView === 'completed-events' ? navigation.eventId : null}
          />
        </ViewPanel>
      )}
      {hasRole('coordinator') && (
        <ViewPanel active={activeView === 'venue-planning'}>
          <div className="grid gap-6 xl:grid-cols-2">
            <VenueSearch />
            <VenueCatalogue />
          </div>
          <VenueCalendar />
        </ViewPanel>
      )}
      {hasRole('coordinator_lead') && (
        <ViewPanel active={activeView === 'unassigned-queue'}>
          <UnassignedQueue />
        </ViewPanel>
      )}
      {hasRole('coordinator_lead') && (
        <ViewPanel active={activeView === 'active-assignments'}>
          <ActiveAssignments
            targetEventId={activeView === 'active-assignments' ? navigation.eventId : null}
          />
        </ViewPanel>
      )}
      {hasRole('venue_staff') && (
        <ViewPanel active={activeView === 'venue-catalogue'}>
          <VenueCatalogue key={venueVersion} onDirtyChange={setVenueFormDirty} />
        </ViewPanel>
      )}
      {hasRole('venue_staff') && (
        <ViewPanel active={activeView === 'booking-decisions'}>
          <VenueBookingDecisions
            targetEventId={activeView === 'booking-decisions' ? navigation.eventId : null}
          />
        </ViewPanel>
      )}
      {hasRole('venue_staff') && (
        <ViewPanel active={activeView === 'booking-problems'}>
          <BookingProblems />
        </ViewPanel>
      )}
      {hasRole('venue_staff') && (
        <ViewPanel active={activeView === 'venue-calendar'}>
          <VenueCalendar />
        </ViewPanel>
      )}
      {hasRole('tech_support') && (
        <ViewPanel active={activeView === 'equipment-catalogue'}>
          <EquipmentCatalogue />
        </ViewPanel>
      )}
      {hasRole('tech_support') && (
        <ViewPanel active={activeView === 'equipment-review'}>
          <EquipmentReviewQueue />
        </ViewPanel>
      )}
      {hasRole('safety_officer') && (
        <ViewPanel active={activeView === 'safety-review'}>
          <SafetyReviewQueue />
        </ViewPanel>
      )}
      <ViewPanel active={activeView === 'notifications'}>
        <NotificationInbox
          allowedViews={items.map((item) => item.id)}
          onNavigate={navigation.navigate}
        />
      </ViewPanel>
    </AppShell>
  )
}

function nav(id: View, group: string, icon: string): NavigationItem {
  return { ...VIEW_DETAILS[id], group, icon }
}

function ViewPanel({
  active,
  children,
  labelledBy,
}: {
  active: boolean
  children: React.ReactNode
  labelledBy?: string
}) {
  return (
    <section aria-labelledby={labelledBy} hidden={!active} className="min-w-0">
      {children}
    </section>
  )
}

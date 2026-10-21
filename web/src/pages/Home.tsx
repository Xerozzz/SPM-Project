import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getHealth } from '../api/client'
import type { EventRequest } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import MyEventRequests from '../components/MyEventRequests'
import ActiveAssignments from '../components/ActiveAssignments'
import NotificationInbox from '../components/NotificationInbox'
import OrganisationEventCalendar from '../components/OrganisationEventCalendar'
import EventRequestForm from '../components/EventRequestForm'
import BookingProblems from '../components/BookingProblems'
import EventRequestReview from '../components/EventRequestReview'
import UnassignedQueue from '../components/UnassignedQueue'
import EquipmentCatalogue from '../components/EquipmentCatalogue'
import EquipmentReviewQueue from '../components/EquipmentReviewQueue'
import SafetyReviewQueue from '../components/SafetyReviewQueue'
import VenueBookingDecisions from '../components/VenueBookingDecisions'
import VenueCalendar from '../components/VenueCalendar'
import VenueCatalogue from '../components/VenueCatalogue'
import VenueSearch from '../components/VenueSearch'

/**
 * Home page, visible only after sign-in. Shows the session roles and a sign-out button.
 */
export default function HomePage() {
  const { roles, signOut, hasRole } = useAuth()
  // Held here because the form and the list are siblings: the list chooses a draft,
  // the form edits it, and neither owns the other.
  const [editingDraft, setEditingDraft] = useState<EventRequest | null>(null)
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <main className="mx-auto max-w-xl p-8 font-sans">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">ConnectSphere</h1>
          <p className="mt-1 text-sm text-slate-500">Signed in as: {roles.join(', ')}</p>
        </div>
        <button
          type="button"
          onClick={signOut}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Sign out
        </button>
      </div>

      {hasRole('organiser') && (
        <>
          <OrganisationEventCalendar />
          {/* One form. Choosing Edit draft in the list below fills in the form above
              rather than opening a second one. */}
          <EventRequestForm editing={editingDraft} onDone={() => setEditingDraft(null)} />
          <MyEventRequests onEditDraft={setEditingDraft} />
        </>
      )}

      {hasRole('coordinator') && <EventRequestReview />}

      {/* SCRUM-101: Coordinator Leads triage newly submitted requests. */}
      {hasRole('coordinator_lead') && <UnassignedQueue />}

      {/* SCRUM-100: Coordinator Leads see every active request and its current owner. */}
      {hasRole('coordinator_lead') && <ActiveAssignments />}

      {/* SCRUM-99: every signed-in user gets a private notification inbox. */}
      <NotificationInbox />

      {hasRole('tech_support') && <EquipmentCatalogue />}

      {/* SCRUM-44 and SCRUM-53: the review routes have existed since SCRUM-44 merged
          with nothing reaching them, so neither story could be shown through the UI. */}
      {hasRole('tech_support') && <EquipmentReviewQueue />}

      {/* SCRUM-79: Safety Officers review the plan an event is being run to. */}
      {hasRole('safety_officer') && <SafetyReviewQueue />}

      {/* SCRUM-55: coordinators search active venues by event requirements. */}
      {hasRole('coordinator') && <VenueSearch />}

      {/* SCRUM-59: Venue Staff maintain the catalogue; coordinators read it for planning. */}
      {(hasRole('venue_staff') || hasRole('coordinator')) && <VenueCatalogue />}

      {/* SCRUM-89: Venue Staff see confirmed bookings that no longer fit their venue. */}
      {hasRole('venue_staff') && <BookingProblems />}

      {/* SCRUM-40: Venue Staff review and decide booking requests. */}
      {hasRole('venue_staff') && <VenueBookingDecisions />}
      {/* SCRUM-54: what holds each venue across a date range. */}
      {(hasRole('venue_staff') || hasRole('coordinator')) && <VenueCalendar />}

      <section className="mt-6 rounded-lg border border-slate-200 p-4">
        <h2 className="font-medium">API health</h2>
        <p className="mt-2 text-sm" role="status">
          {health.isPending && 'Checking the API…'}
          {health.isError && `Cannot reach the API: ${health.error.message}`}
          {health.data && `API and database are ${health.data.status}`}
        </p>
      </section>
    </main>
  )
}

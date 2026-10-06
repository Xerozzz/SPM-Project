# ConnectSphere Event Flow

## How to read this flow

This is one end-to-end workflow based on the Week 4 Release 1 core requirements and
Customer Clarifications 1 and 2. Week 7 changes are included at the affected step rather
than in a separate flow:

- ~~Strikethrough~~ means the previous, now-legacy rule.
- **Bold** means the Week 7 replacement or addition that must be implemented for Release 1.

Where Week 7 conflicts with the earlier requirements or clarifications, the Week 7 rule wins.
This is a target business workflow, not a statement that every step is already implemented in
the current codebase.

---

## End-to-end event flow

### 1. Access and event request preparation

1. Users sign in with the role or roles assigned to their account. A person may hold multiple
   roles; account creation and organisation onboarding are outside Release 1.
2. An Event Organiser creates an event request with the planning information needed by
   ConnectSphere: name, purpose, description, date/time, expected attendance, venue,
   accessibility, equipment, layout, and registration requirements.
3. The organiser may save an incomplete request as a **Draft**, edit it later, or delete it.
   Drafts do not automatically expire.
4. The organiser submits a complete request. After submission, the organiser cannot directly
   edit it; changes are requested through the Event Coordinator.

### 2. Assignment and initial review

5. ~~The system automatically assigns exactly one Event Coordinator fairly using round robin.~~
   **The submitted request enters an unassigned queue. The Event Coordinator Lead reviews
   basic event information and assigns an appropriate Event Coordinator.**
6. ~~If reassignment is needed, the outgoing coordinator initiates it after agreement with
   the replacement coordinator.~~ **The Event Coordinator Lead may reassign events and can
   view all coordinator assignments and active events under their supervision.**
7. The assigned coordinator reviews the request. Coordinators may view other events for
   planning, but may edit or decide only events assigned to them.
8. If information is incomplete or unclear, the coordinator requests clarification from the
   organiser. Clarification is part of review, not a separate required event status.
9. The coordinator approves the request for planning or rejects it with a free-text reason.
   A rejected request remains recorded; the organiser may revise and resubmit it.
10. **Relevant users are notified when an assignment or reassignment occurs.**

### 3. Venue catalogue, calendar, search, and suitability

11. Venue Staff maintain the Venue Catalogue by creating, editing, and deleting venue records,
    including capacity, location, facilities, accessibility, layouts, operating information,
    **setup time, and turnaround time.**
12. Authorised internal users use the Venue Availability Calendar to view venues across
    relevant dates and times. It shows confirmed bookings and recorded unavailability, such
    as maintenance.
13. ~~The calendar and availability checks use only the advertised event start and end time.~~
    **They use the full occupied period, including configurable setup time before the event
    and turnaround time after it. The calendar displays this buffered period.** For example,
    an event from 10:00 to 12:00 with 30 minutes of setup and 45 minutes of turnaround
    occupies the venue from 09:30 to 12:45.
14. **Existing bookings that become problematic under the buffered-time rule are identified;
    they are not silently removed.**
15. For an approved event, the coordinator searches the Venue Catalogue using date/time,
    capacity, location, accessibility, supported layout, and facilities. Search results include
    active venues available for the requested time range.
16. The coordinator uses suitability information as advisory guidance. Capacity,
    accessibility, layout, and facility mismatches are shown so the coordinator can make an
    informed decision.

### 4. Venue booking requests, holds, and staff decisions

17. ~~The coordinator submits one venue-booking request for each event.~~ **The coordinator
    may submit a booking request for each venue needed by one event, such as a main space and
    breakout rooms. Each venue is checked independently for suitability, availability, and
    conflicts.**
18. Pending booking requests do not block availability; confirmed bookings and recorded venue
    unavailability do. Pending conflicts may be resolved outside the system.
19. **Venue Staff may place a tentative hold while arrangements are being finalised. A hold
    has an expiry date/time, appears on the availability calendar, and temporarily reserves the
    venue. The coordinator is informed before or when it expires. An expired hold is not a
    confirmed booking and the venue becomes available again.**
20. Venue Staff review each pending venue request independently and approve or reject it. A
    rejection reason is appropriate; suggesting an alternative venue is optional. A confirmed
    booking prevents overlapping confirmed bookings and affects later venue searches.
21. ~~One venue arrangement is the event's only venue arrangement.~~ **Changing or cancelling
    one venue arrangement does not automatically remove the event's other venue bookings unless
    this is explicitly required.** Venue Staff do not alter a confirmed booking directly; the
    coordinator initiates any required change.

### 5. Venue becomes unavailable after booking

22. Venue Staff may record temporary venue unavailability for maintenance, equipment failure,
    renovation, safety concerns, or other operational reasons.
23. **If new unavailability overlaps future bookings, the system identifies the affected
    booking(s) and informs the relevant Event Coordinator(s). The event is not automatically
    cancelled: its information is preserved while the coordinator searches for and requests a
    replacement venue.**

### 6. Equipment planning and reservation

24. The coordinator records requested equipment, quantities, and technical requirements.
25. Technical Support Staff review the request, check equipment availability for the event
    time, and reserve suitable equipment. Equipment reserved for an overlapping event or marked
    unavailable is not treated as available.
26. The coordinator may add or remove equipment before confirmation. Technical Support Staff
    re-check suitability and availability after those changes.

### 7. Safety approval, confirmation, and registration

27. ~~Once essential venue and equipment arrangements are approved, the Event Coordinator
    confirms the event.~~ **After venue and technical arrangements are confirmed, a Safety
    Officer performs an Operational Safety Check before the event can proceed to preparation.**
28. **The Safety Officer reviews attendance, capacity/layout, emergency access, accessibility,
    equipment placement, crowd movement, and known venue restrictions. The officer may approve,
    reject, or request changes. Requested changes return the event to the relevant earlier
    planning stage and may require venue or technical arrangements to be reviewed again.**
29. When all essential arrangements and the required safety approval are complete, the Event
    Coordinator confirms the event.
30. If registration is enabled, attendees may view the confirmed event, register, view their
    registration status, and withdraw. Registration opens after confirmation; the organiser may
    manually open, extend, or close it and controls capacity. First-come-first-served and a
    waiting list apply where enabled.

### 8. Changes, cancellation, delivery, and completion

31. During planning, authorised users may make ordinary information updates. After submission,
    an organiser requests changes through the coordinator.
32. Significant changes to date/time, attendance, venue, or equipment require venue,
    equipment, technical-support, and registration arrangements to be reconsidered where
    affected. A confirmed event returns to planning when a major change is accepted for review.
33. A cancelled event is terminal. Related venue and equipment reservations must no longer
    remain committed; a similar replacement event requires a new request.
34. Venue Staff and Technical Support prepare the confirmed venue and equipment. After the
    event, authorised users record operational notes and mark the event **Completed**.

## Cross-cutting rules

- Event statuses communicate the current stage, including Draft, Submitted, Under Review /
  Planning, Approved, Confirmed, Completed, Cancelled, and Rejected.
- Organisers in the same organisation can view their organisation's event calendar, subject to
  role and relationship-based access rules.
- Important actions and changes are auditable. Coordinators and organisers can view who changed
  relevant information, what changed, and when it changed.
- Relevant users receive notifications for submissions, clarification requests, decisions,
  venue booking decisions, changes, confirmation, cancellation, registration updates, and
  **assignment/reassignment, tentative-hold reminders and expiry, venue disruptions affecting
  bookings, and Safety Officer outcomes.**
- The system reminds relevant users about incomplete arrangements; reminder frequency is
  configurable.

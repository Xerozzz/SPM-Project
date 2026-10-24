# ADR-0057: Keep manual registration decision notes in registration history

## Status

Proposed

## Context

SCRUM-134 lets an Event Organiser accept or waitlist an existing attendee registration and
optionally explain that decision. SCRUM-42 already made `event_registration_history` the
append-only source action for every registration status transition, but it cannot retain a note.

## Decision

Add one nullable `note` column to `event_registration_history`. A manual decision appends its
actor, UTC occurrence time, previous and new status, and its cleaned optional note in the same
transaction that changes the existing registration row. Submission and withdrawal history leave
the column null.

## Consequences

There is one chronological audit/source-action stream for all registration status changes; no
parallel decision or notification table is introduced. A later notification story can consume the
committed history row without changing the registration lifecycle.

## Alternatives considered

Store the note on `event_registrations`: rejected because the next decision would overwrite the
previous explanation. Create a decision table: rejected because it would duplicate SCRUM-42's
history/source-action responsibility.

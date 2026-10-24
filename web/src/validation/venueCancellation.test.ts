import { expect, test } from 'vitest'

import type { BookingStatus, EventStatus, VenueBooking } from '../api/eventRequests'
import { canOfferCancel, describeCanceller } from './venueCancellation'

// SCRUM-109: when "Cancel arrangement" is offered. The API is the real guard.

const NOW = new Date('2030-01-05T09:00:00Z')
const EVENT = { status: 'approved' as EventStatus, coordinator_id: 'coordinator-1' }

function booking(status: BookingStatus, expires_at: string | null = null): VenueBooking {
  return {
    id: 'booking-1',
    venue_id: 'venue-1',
    session_label: 'Morning workshop',
    start_at: '2030-01-10T02:00:00Z',
    end_at: '2030-01-10T06:00:00Z',
    status,
    expires_at,
    conflict: null,
  }
}

test.each([
  ['pending', null, true],
  ['confirmed', null, true],
  ['tentative', '2030-01-05T09:00:01Z', true],
  ['tentative', '2030-01-05T09:00:00Z', false],
  ['tentative', '2030-01-05T08:59:59Z', false],
  ['cancelled', null, false],
  ['rejected', null, false],
  ['expired', '2030-01-05T08:00:00Z', false],
] as const)(
  'SCRUM-109: a %s booking (hold until %s) offers cancel: %s',
  (status, until, offered) => {
    expect(canOfferCancel(booking(status, until), EVENT, 'coordinator-1', NOW)).toBe(offered)
  },
)

test.each(['draft', 'submitted', 'rejected', 'confirmed'] as const)(
  'SCRUM-109: nothing is offered while the event is %s',
  (status) => {
    expect(canOfferCancel(booking('pending'), { ...EVENT, status }, 'coordinator-1', NOW)).toBe(
      false,
    )
  },
)

test('SCRUM-109: nothing is offered to anyone but the assigned Coordinator', () => {
  expect(canOfferCancel(booking('pending'), EVENT, 'coordinator-2', NOW)).toBe(false)
  expect(canOfferCancel(booking('pending'), EVENT, null, NOW)).toBe(false)
  expect(
    canOfferCancel(booking('pending'), { ...EVENT, coordinator_id: null }, 'coordinator-1', NOW),
  ).toBe(false)
})

test('SCRUM-109: the canceller is "you" or another coordinator, never a raw id', () => {
  expect(describeCanceller('coordinator-1', 'coordinator-1')).toBe('Cancelled by you')
  expect(describeCanceller('coordinator-9', 'coordinator-1')).toBe(
    'Cancelled by another coordinator',
  )
  expect(describeCanceller(null, 'coordinator-1')).toBe('Cancelled by another coordinator')
})

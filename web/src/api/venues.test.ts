import { afterEach, expect, test, vi } from 'vitest'

import { createVenueUnavailability, searchVenues } from './venues'

afterEach(() => {
  vi.restoreAllMocks()
})

test('TC-55-AC1-02: Singapore wall-clock search values are sent as UTC instants', async () => {
  let requested = ''
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    requested = String(input)
    return new Response(JSON.stringify([]), { status: 200 })
  })

  await searchVenues('token', {
    startDate: '2026-12-01',
    startTime: '10:00',
    endDate: '2026-12-03',
    endTime: '12:00',
  })

  const query = new URL(requested, 'http://example.test').searchParams
  expect(query.get('start_at')).toBe('2026-12-01T02:00:00.000Z')
  expect(query.get('end_at')).toBe('2026-12-03T04:00:00.000Z')
})

test('a refused closure reports the reason the server gave, not just a status code', async () => {
  // The 409 exists to say a confirmed booking is in the way. Reporting "(409)" instead
  // leaves Venue Staff with a number and no idea what to do about it.
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          detail:
            'This venue is already committed to a confirmed booking for part of that period, so it cannot be closed. Booking abc.',
        }),
        { status: 409 },
      ),
  )

  await expect(
    createVenueUnavailability('token', 'venue-1', {
      starts_at: '2030-01-01T00:00:00Z',
      ends_at: '2030-01-01T02:00:00Z',
      reason: 'Maintenance',
    }),
  ).rejects.toThrow('already committed to a confirmed booking')
})

test('a refused closure with no explanation still reports something', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response('gateway down', { status: 502 }),
  )

  await expect(
    createVenueUnavailability('token', 'venue-1', {
      starts_at: '2030-01-01T00:00:00Z',
      ends_at: '2030-01-01T02:00:00Z',
      reason: 'Maintenance',
    }),
  ).rejects.toThrow('could not be saved (502)')
})

import { afterEach, expect, test, vi } from 'vitest'

import { searchVenues } from './venues'

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

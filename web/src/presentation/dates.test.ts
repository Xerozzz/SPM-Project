import { expect, test } from 'vitest'

import { formatSingaporeTime } from '../api/venueCalendar'
import { formatDateRange, formatDisplayTime, sessionOnDay, singaporeDay } from './dates'

// SCRUM-46 / SCRUM-40: concise summaries still represent the same UTC instants.
test('formats an instant in Singapore time without seconds', () => {
  expect(formatDisplayTime('2026-11-30T02:00:12Z')).toBe('30 Nov 2026 · 10:00 am SGT')
})
test('prints the date once for sessions on the same Singapore day', () => {
  expect(formatDateRange('2026-11-30T02:00:00Z', '2026-11-30T06:00:00Z')).toBe(
    '30 Nov 2026 · 10:00 am–2:00 pm SGT',
  )
})
test('keeps both dates when a session crosses Singapore midnight', () => {
  expect(formatDateRange('2030-01-01T15:00:00Z', '2030-01-01T17:00:00Z')).toBe(
    '1 Jan 2030 · 11:00 pm SGT – 2 Jan 2030 · 1:00 am SGT',
  )
  expect(singaporeDay('2030-01-01T16:00:00Z')).toBe('2030-01-02')
})
test('audit timestamps retain their seconds', () => {
  expect(formatSingaporeTime('2030-01-01T02:00:12Z')).toContain('10:00:12')
})

test('day filtering includes overnight sessions and excludes an exclusive midnight end', () => {
  expect(sessionOnDay('2030-01-01T15:00:00Z', '2030-01-01T17:00:00Z', '2030-01-02')).toBe(true)
  expect(sessionOnDay('2030-01-01T15:00:00Z', '2030-01-01T16:00:00Z', '2030-01-02')).toBe(false)
})

import { expect, test } from 'vitest'
import { matchesSearch } from './search'

// SCRUM-46 / SCRUM-59: search only filters already-loaded permitted records.
test('finds words across names and venue fields regardless of case', () => {
  expect(matchesSearch('orientation HALL', 'Orientation Day', 'Hall A')).toBe(true)
  expect(matchesSearch('orientation studio', 'Orientation Day', 'Hall A')).toBe(false)
})
test('blank queries and incomplete drafts are supported', () => {
  expect(matchesSearch('  ', null, undefined)).toBe(true)
  expect(matchesSearch('workshop', null, 'Hall A')).toBe(false)
})

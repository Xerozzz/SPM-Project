import { expect, test } from 'vitest'

import { hasReviewNote } from './eventRequestReview'

test('rejects an empty review note', () => {
  expect(hasReviewNote('')).toBe(false)
})

test('rejects a whitespace-only review note', () => {
  expect(hasReviewNote('   ')).toBe(false)
})

test('accepts a non-blank review note', () => {
  expect(hasReviewNote('Needs a safer venue')).toBe(true)
})
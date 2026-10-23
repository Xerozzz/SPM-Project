import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import type { SafetyReview } from '../api/safetyReviews'
import InvalidatedNote from './InvalidatedNote'

const APPROVAL: SafetyReview = {
  id: 'review-1',
  event_request_id: 'event-1',
  decision: 'approve',
  comment: 'Egress is clear.',
  plan_fingerprint: 'fingerprint-abc',
  decided_by_id: 'officer-1',
  decided_at: '2029-12-01T02:00:00Z',
  returns_to_coordinator: false,
}

test('an approval that still counts shows nothing extra', () => {
  const { container } = render(<InvalidatedNote review={APPROVAL} />)
  expect(container).toBeEmptyDOMElement()
})

test('an invalidated approval says when and why', () => {
  render(
    <InvalidatedNote
      review={{
        ...APPROVAL,
        invalidated_at: '2029-12-02T02:00:00Z',
        invalidation_cause: 'change_request',
      }}
    />,
  )
  expect(screen.getByText(/No longer valid since/)).toHaveTextContent(
    'after an approved change. The plan needs a new review.',
  )
})

test('a closure is named as the cause', () => {
  render(
    <InvalidatedNote
      review={{
        ...APPROVAL,
        invalidated_at: '2029-12-02T02:00:00Z',
        invalidation_cause: 'venue_closure',
      }}
    />,
  )
  expect(screen.getByText(/after a venue closure/)).toBeInTheDocument()
})

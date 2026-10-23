import type { SafetyReview } from '../api/safetyReviews'
import { formatSingaporeTime } from '../api/venueCalendar'

/** SCRUM-130: why an approval stopped counting. Kept in the history, never removed. */
const CAUSES: Record<string, string> = {
  change_request: 'an approved change',
  venue_closure: 'a venue closure',
}

export default function InvalidatedNote({ review }: { review: SafetyReview }) {
  if (!review.invalidated_at) return null
  const cause = CAUSES[review.invalidation_cause ?? ''] ?? 'a change'
  return (
    <span className="block text-amber-800">
      No longer valid since {formatSingaporeTime(review.invalidated_at)}: the event went back to
      planning after {cause}. The plan needs a new review.
    </span>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { REVIEW_LABELS } from '../api/equipmentRequirements'
import {
  DECISION_LABELS,
  describeBlocker,
  type EventPlan,
  listDecisions,
  listPlansToReview,
  PlanNotReviewableError,
  type SafetyDecision,
  recordDecision,
  SAFETY_DECISIONS,
} from '../api/safetyReviews'
import { STATUS_LABELS } from '../api/venueBookingDecisions'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import InvalidatedNote from './InvalidatedNote'

function name(plan: EventPlan): string {
  return plan.event_name ?? 'Untitled event'
}

/** SCRUM-53's states, said plainly. The Officer cares how much is actually secured. */
const RESERVATION_LABELS: Record<string, string> = {
  not_reserved: 'nothing reserved',
  partially_reserved: 'partly reserved',
  reserved: 'reserved',
}

/** What came back from one decision, kept against the event it was about. */
interface Answer {
  eventId: string
  text: string
  blockers: string[]
}

/**
 * SCRUM-79: what a Safety Officer has to review, and what they decide about it.
 *
 * The worklist carries each event's whole plan (AC1 and AC3), so the Officer reads the
 * venue arrangements and equipment that a decision is actually about without opening
 * anything. Events that are not ready are listed too, with what is still missing (AC2),
 * rather than being hidden until a Coordinator finishes.
 *
 * The two groups are not decoration. Every event being planned appears here, and on a
 * real board most of them are waiting on a Coordinator; with one list the Officer scrolls
 * past twenty cards they can do nothing about to reach the one they can.
 *
 * Every rule stays on the API. What blocks a review, whether the plan has moved since it
 * was read (AC7) and what a decision means for the event (AC8: an approval does not
 * confirm it) are its decisions; this sends the decision and shows the answer.
 */
export default function SafetyReviewQueue() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [comments, setComments] = useState<Record<string, string>>({})
  const [showing, setShowing] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<Answer | null>(null)
  const [failure, setFailure] = useState<Answer | null>(null)
  const [selectedTab, setSelectedTab] = useState<'ready' | 'waiting'>('ready')

  const queryKey = ['safety-reviews', token]
  const worklist = useQuery({
    queryKey,
    queryFn: () => listPlansToReview(token ?? ''),
    enabled: token !== null,
    // Not on window focus, unlike the rest of the app. AC7 exists so a decision cannot
    // authorise a plan nobody read, and a background refresh defeats it from the client
    // side: the plan is swapped under the Officer mid-read and the fingerprint quietly
    // follows, so the stale check passes on a plan they never saw. Observed in the
    // browser, where switching away and back silently picked up an added requirement
    // and approved it. The plan now changes only when the Officer reloads or after
    // their own decision; if it moved meanwhile the API refuses and says to read again.
    refetchOnWindowFocus: false,
  })

  const decide = useMutation({
    mutationFn: (input: { plan: EventPlan; decision: SafetyDecision }) =>
      recordDecision(
        token ?? '',
        input.plan.event_request_id,
        input.decision,
        comments[input.plan.event_request_id] ?? '',
        input.plan.plan_fingerprint,
      ),
    onError: (error: Error, input) => {
      setFailure({
        eventId: input.plan.event_request_id,
        text: error.message,
        blockers: error instanceof PlanNotReviewableError ? error.blockers : [],
      })
      // Either refusal means the list is out of date: something moved after it loaded,
      // or a prerequisite was cleared or broken. Reload so the card tells the truth and
      // the Officer is deciding against the plan that is actually there.
      void client.invalidateQueries({ queryKey })
    },
    onSuccess: (recorded, input) => {
      setOutcome({
        eventId: input.plan.event_request_id,
        text: recorded.returns_to_coordinator
          ? `${DECISION_LABELS[recorded.decision]} recorded for ${name(input.plan)}. The Coordinator has been notified.`
          : // AC8: approving the plan does not confirm the event. Saying so here keeps
            // the Officer from thinking they have booked anything.
            `Safety approved for ${name(input.plan)}. This does not confirm the event.`,
        blockers: [],
      })
      setComments((all) => ({ ...all, [input.plan.event_request_id]: '' }))
      void client.invalidateQueries({ queryKey })
    },
  })

  function card(plan: EventPlan) {
    return (
      <PlanCard
        key={plan.event_request_id}
        plan={plan}
        comment={comments[plan.event_request_id] ?? ''}
        busy={decide.isPending}
        // Answers are shown on the card that was acted on. At the foot of the section
        // they were thousands of pixels below the button that caused them, so a refused
        // decision looked like nothing had happened at all.
        outcome={outcome?.eventId === plan.event_request_id ? outcome : null}
        failure={failure?.eventId === plan.event_request_id ? failure : null}
        historyOpen={showing === plan.event_request_id}
        onComment={(text) => setComments((all) => ({ ...all, [plan.event_request_id]: text }))}
        onToggleHistory={() =>
          setShowing(showing === plan.event_request_id ? null : plan.event_request_id)
        }
        onDecide={(decision) => {
          setOutcome(null)
          setFailure(null)
          decide.mutate({ plan, decision })
        }}
      />
    )
  }

  const ready = worklist.data?.filter((plan) => plan.may_review) ?? []
  const waiting = worklist.data?.filter((plan) => !plan.may_review) ?? []

  return (
    <section>
      {worklist.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {worklist.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {worklist.error.message}
        </p>
      )}
      {worklist.isSuccess && worklist.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No events are being planned.</p>
      )}

      {worklist.isSuccess && worklist.data.length > 0 && (
        <>
          <div
            role="tablist"
            aria-label="Safety review status"
            className="mt-5 flex gap-2 border-b border-slate-200 pb-3"
          >
            <button
              type="button"
              role="tab"
              aria-selected={selectedTab === 'ready'}
              onClick={() => setSelectedTab('ready')}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${selectedTab === 'ready' ? 'bg-[#202124] text-white' : 'bg-white text-slate-600'}`}
            >
              Ready to review <span className="ml-1 opacity-70">{ready.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={selectedTab === 'waiting'}
              onClick={() => setSelectedTab('waiting')}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${selectedTab === 'waiting' ? 'bg-[#202124] text-white' : 'bg-white text-slate-600'}`}
            >
              Waiting on arrangements <span className="ml-1 opacity-70">{waiting.length}</span>
            </button>
          </div>
          {selectedTab === 'ready' &&
            (ready.length === 0 ? (
              <p className="mt-1 text-sm text-slate-500">
                Nothing is arranged enough to review yet.
              </p>
            ) : (
              ready.map(card)
            ))}
          {selectedTab === 'waiting' &&
            (waiting.length === 0 ? (
              <p className="mt-1 text-sm text-slate-500">
                Every event being planned is ready to review.
              </p>
            ) : (
              waiting.map(card)
            ))}
        </>
      )}
    </section>
  )
}

/** One event's plan, what it is waiting on or what may be decided, and the answer. */
function PlanCard({
  plan,
  comment,
  busy,
  outcome,
  failure,
  historyOpen,
  onComment,
  onToggleHistory,
  onDecide,
}: {
  plan: EventPlan
  comment: string
  busy: boolean
  outcome: Answer | null
  failure: Answer | null
  historyOpen: boolean
  onComment: (text: string) => void
  onToggleHistory: () => void
  onDecide: (decision: SafetyDecision) => void
}) {
  return (
    <article className="mt-4 rounded border border-slate-200 p-3 text-sm">
      <h4 className="font-medium">{name(plan)}</h4>
      {plan.event_start_at && plan.event_end_at && (
        <p className="text-slate-500">
          {formatSingaporeTime(plan.event_start_at)} to {formatSingaporeTime(plan.event_end_at)}
        </p>
      )}
      <p className="text-slate-500">
        {plan.expected_attendance === null
          ? 'No expected attendance recorded'
          : `${plan.expected_attendance} expected`}
      </p>
      {plan.accessibility_requirement && (
        <p className="text-slate-500">Accessibility: {plan.accessibility_requirement}</p>
      )}
      {plan.layout_requirement && (
        <p className="text-slate-500">Layout: {plan.layout_requirement}</p>
      )}

      <h5 className="mt-3 font-medium">Venues</h5>
      {plan.venues.length === 0 ? (
        <p className="text-slate-500">Nothing arranged.</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {plan.venues.map((venue) => (
            <li key={venue.booking_id}>
              <span className="font-medium">{venue.session_label}</span>{' '}
              {formatSingaporeTime(venue.start_at)} to {formatSingaporeTime(venue.end_at)}{' '}
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                {STATUS_LABELS[venue.status]}
              </span>
              {/* ADR-0030 expires a hold by a sweep, so a hold can read as tentative
                  after it has run out. Safety must not rest on one of those. */}
              {venue.hold_expired && (
                <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                  Hold has run out
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <h5 className="mt-3 font-medium">Equipment</h5>
      {plan.equipment.length === 0 ? (
        <p className="text-slate-500">None requested.</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {plan.equipment.map((item) => (
            <li key={item.requirement_id}>
              {item.equipment_type} &times;{item.quantity}{' '}
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                {REVIEW_LABELS[item.review_status]}
              </span>{' '}
              <span className="text-xs text-slate-500">
                {RESERVATION_LABELS[item.reservation_state]}
              </span>
              {item.has_flagged_reservation && (
                <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                  Reservation to reconsider
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* AC5: a rejection or a request for changes stays visible until the plan is
          reviewed again, because the Coordinator has to act on it. */}
      {plan.latest_decision && (
        <p className="mt-3 rounded bg-slate-50 p-2">
          <span className="font-medium">{DECISION_LABELS[plan.latest_decision.decision]}</span> on{' '}
          {formatSingaporeTime(plan.latest_decision.decided_at)}: {plan.latest_decision.comment}
          <InvalidatedNote review={plan.latest_decision} />
        </p>
      )}

      {plan.may_review ? (
        <DecisionForm
          plan={plan}
          comment={comment}
          busy={busy}
          onComment={onComment}
          onDecide={onDecide}
        />
      ) : (
        <div className="mt-3 rounded bg-amber-50 p-2 text-amber-900">
          <p className="font-medium">This plan cannot be reviewed yet.</p>
          <ul className="mt-1 list-disc pl-5">
            {plan.blockers.map((blocker) => (
              <li key={blocker}>{describeBlocker(blocker)}</li>
            ))}
          </ul>
        </div>
      )}

      {failure && (
        <div role="alert" className="mt-3 text-red-600">
          <p>{failure.text}</p>
          {failure.blockers.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {failure.blockers.map((blocker) => (
                <li key={blocker}>{describeBlocker(blocker)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {outcome && (
        <p role="status" className="mt-3 text-green-700">
          {outcome.text}
        </p>
      )}

      <button type="button" onClick={onToggleHistory} className="mt-3 underline">
        {historyOpen ? 'Hide past decisions' : 'Past decisions'}
      </button>
      {historyOpen && <History eventId={plan.event_request_id} />}
    </article>
  )
}

/**
 * AC4: the three decisions, each needing a reason.
 *
 * The comment is required by the API and required here, so the Officer is told before
 * they click rather than after. The fingerprint travels with the decision, which is why
 * it is read off this plan rather than from anywhere else.
 */
function DecisionForm({
  plan,
  comment,
  busy,
  onComment,
  onDecide,
}: {
  plan: EventPlan
  comment: string
  busy: boolean
  onComment: (text: string) => void
  onDecide: (decision: SafetyDecision) => void
}) {
  const fieldId = `safety-comment-${plan.event_request_id}`
  return (
    <div className="mt-3">
      <label className="block font-medium" htmlFor={fieldId}>
        Reason for this decision
      </label>
      <textarea
        id={fieldId}
        value={comment}
        onChange={(event) => onComment(event.target.value)}
        className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        {SAFETY_DECISIONS.map((decision) => (
          <button
            key={decision}
            type="button"
            disabled={busy || comment.trim() === ''}
            aria-label={`${DECISION_LABELS[decision]} the plan for ${name(plan)}`}
            onClick={() => onDecide(decision)}
            className={`rounded px-3 py-1.5 text-sm text-white disabled:opacity-50 ${
              decision === 'reject' ? 'bg-red-700' : 'bg-slate-900'
            }`}
          >
            {DECISION_LABELS[decision]}
          </button>
        ))}
      </div>
      {comment.trim() === '' && (
        <p className="mt-1 text-xs text-slate-500">A reason is needed to record a decision.</p>
      )}
    </div>
  )
}

/** AC9: every decision on this event, loaded only when asked for. */
function History({ eventId }: { eventId: string }) {
  const { token } = useAuth()
  const history = useQuery({
    queryKey: ['safety-review-history', eventId, token],
    queryFn: () => listDecisions(token ?? '', eventId),
    enabled: token !== null,
  })

  if (history.isPending) return <p className="mt-2">Loading…</p>
  if (history.isError) {
    return (
      <p role="alert" className="mt-2 text-red-600">
        {history.error.message}
      </p>
    )
  }
  if (history.data.length === 0) {
    return <p className="mt-2 text-slate-500">No decision has been recorded yet.</p>
  }
  return (
    <ul className="mt-2 space-y-1">
      {history.data.map((review) => (
        <li key={review.id}>
          <span className="font-medium">{DECISION_LABELS[review.decision]}</span> on{' '}
          {formatSingaporeTime(review.decided_at)}: {review.comment}
          <InvalidatedNote review={review} />
        </li>
      ))}
    </ul>
  )
}

import { describe, expect, test } from 'vitest'

import type { ChangePlan } from '../api/eventChangeRequests'
import { acceptsChangeRequest, changeRequestOf, draftOf } from './eventChange'

const plan: ChangePlan = {
  event: {
    start_at: '2026-12-01T01:00:00Z',
    end_at: '2026-12-01T05:00:00Z',
    expected_attendance: 100,
    venue_requirement: 'Hall A',
    accessibility_requirement: 'Step-free access',
    layout_requirement: 'Theatre',
  },
  sessions: [
    {
      id: 's-1',
      session_label: 'Keynote',
      start_at: '2026-12-01T01:00:00Z',
      end_at: '2026-12-01T02:00:00Z',
    },
  ],
  equipment: [
    { id: 'e-1', equipment_type: 'Projector', quantity: 2, technical_requirements: null },
  ],
  venue_options: ['Hall A', 'Hall B'],
  equipment_types: ['Microphone', 'Projector'],
}

describe('SCRUM-37 change request body', () => {
  test('AC1 and AC7: only submitted, approved and confirmed events take a proposal', () => {
    expect(acceptsChangeRequest('submitted')).toBe(true)
    expect(acceptsChangeRequest('approved')).toBe(true)
    expect(acceptsChangeRequest('confirmed')).toBe(true)
    expect(acceptsChangeRequest('draft')).toBe(false)
    expect(acceptsChangeRequest('rejected')).toBe(false)
  })

  test('an untouched form proposes nothing', () => {
    const body = changeRequestOf(plan, draftOf(plan), 'key-1')

    expect(body).toEqual({
      submission_key: 'key-1',
      reason: '',
      event: {},
      sessions: [],
      equipment: [],
    })
  })

  test('AC2: sends only the values that changed, as the API expects them', () => {
    const draft = draftOf(plan)
    draft.reason = 'More people'
    draft.event.expected_attendance = '150'
    draft.event.venue_requirement = 'Hall B'
    draft.sessions[0].label = 'Opening'
    draft.equipment[0].quantity = '3'
    draft.added.push({ type: 'Microphone', quantity: '4' })

    const body = changeRequestOf(plan, draft, 'key-2')

    expect(body.event).toEqual({ expected_attendance: 150, venue_requirement: 'Hall B' })
    expect(body.sessions).toEqual([{ booking_id: 's-1', session_label: 'Opening' }])
    expect(body.equipment).toEqual([
      { requirement_id: 'e-1', quantity: 3 },
      { equipment_type: 'Microphone', quantity: 4 },
    ])
  })

  test('dates go to the API as UTC, and a cleared date as null', () => {
    const draft = draftOf(plan)
    draft.event.start_at = ''
    draft.sessions[0].end = draftOf(plan).sessions[0].start

    const body = changeRequestOf(plan, draft, 'key-3')

    expect(body.event).toEqual({ start_at: null })
    expect(body.sessions[0].end_at).toBe('2026-12-01T01:00:00.000Z')
  })

  test('removing a line sends only the removal', () => {
    const draft = draftOf(plan)
    draft.equipment[0] = { ...draft.equipment[0], remove: true, quantity: '9' }

    expect(changeRequestOf(plan, draft, 'k').equipment).toEqual([
      { requirement_id: 'e-1', remove: true },
    ])
  })
})

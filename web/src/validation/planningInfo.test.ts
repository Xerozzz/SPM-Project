import { expect, test } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import {
  acceptsOrdinaryUpdate,
  blankPlanningFields,
  changedPlanningInfo,
  ORDINARY_FIELDS,
  planningInfoOf,
} from './planningInfo'

// SCRUM-36: the form rules for ordinary planning updates.

const request = {
  name: 'Orientation Day',
  purpose: 'Welcome students',
  description: null,
  accessibility_requirement: 'Step-free access',
  layout_requirement: 'Theatre',
  registration_requirement: 'Open',
} as unknown as EventRequest

test('SCRUM-36 AC3: the ordinary fields leave out date, attendance, venue and equipment', () => {
  const fields: string[] = ORDINARY_FIELDS.map(([field]) => field)

  for (const protectedField of [
    'start_at',
    'end_at',
    'expected_attendance',
    'venue_requirement',
    'equipment_requirement',
  ]) {
    expect(fields).not.toContain(protectedField)
  }
  expect(fields).toHaveLength(6)
})

test('SCRUM-36: a missing value is shown as empty text', () => {
  expect(planningInfoOf(request).description).toBe('')
})

test('SCRUM-36: only changed fields are sent', () => {
  const draft = { ...planningInfoOf(request), layout_requirement: 'Banquet' }

  expect(changedPlanningInfo(request, draft)).toEqual({ layout_requirement: 'Banquet' })
  expect(changedPlanningInfo(request, planningInfoOf(request))).toEqual({})
})

test('SCRUM-36: blank and whitespace-only fields are reported', () => {
  const draft = { ...planningInfoOf(request), name: '   ' }

  expect(blankPlanningFields(draft)).toEqual(['name', 'description'])
})

test('SCRUM-36 AC1: only Submitted and Approved events offer ordinary edits', () => {
  expect(acceptsOrdinaryUpdate('submitted')).toBe(true)
  expect(acceptsOrdinaryUpdate('approved')).toBe(true)
  expect(acceptsOrdinaryUpdate('confirmed')).toBe(false)
  expect(acceptsOrdinaryUpdate('draft')).toBe(false)
  expect(acceptsOrdinaryUpdate('rejected')).toBe(false)
})

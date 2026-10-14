import type { EventRequest } from '../api/eventRequests'

/**
 * SCRUM-36: the ordinary planning fields the assigned coordinator may change, with their
 * labels. Mirrors ORDINARY_FIELDS in api/domain/event_request.py. Date/time, attendance,
 * venue and equipment are not here because they need change control (AC3).
 */
export const ORDINARY_FIELDS = [
  ['name', 'Name'],
  ['purpose', 'Purpose'],
  ['description', 'Description'],
  ['accessibility_requirement', 'Accessibility'],
  ['layout_requirement', 'Layout'],
  ['registration_requirement', 'Registration'],
] as const

export type OrdinaryField = (typeof ORDINARY_FIELDS)[number][0]
export type PlanningInfo = Record<OrdinaryField, string>

/** The current ordinary values of a request, as form text. */
export function planningInfoOf(request: EventRequest): PlanningInfo {
  return Object.fromEntries(
    ORDINARY_FIELDS.map(([field]) => [field, request[field] ?? '']),
  ) as PlanningInfo
}

/** Only the fields the coordinator actually changed, so the update sends nothing else. */
export function changedPlanningInfo(
  request: EventRequest,
  draft: PlanningInfo,
): Partial<PlanningInfo> {
  const current = planningInfoOf(request)
  return Object.fromEntries(
    ORDINARY_FIELDS.filter(([field]) => draft[field] !== current[field]).map(([field]) => [
      field,
      draft[field],
    ]),
  )
}

/** Fields left blank. They are required once submitted, so the API would refuse them. */
export function blankPlanningFields(draft: PlanningInfo): OrdinaryField[] {
  return ORDINARY_FIELDS.filter(([field]) => draft[field].trim().length === 0).map(
    ([field]) => field,
  )
}

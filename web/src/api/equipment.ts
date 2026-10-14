/** Equipment catalogue API calls (SCRUM-84). */

export interface Equipment {
  id: string
  equipment_type: string
  description: string | null
  total_quantity: number
  location: string
  operational_status: OperationalStatus
  is_active: boolean
}

export const OPERATIONAL_STATUSES = ['Operational', 'Damaged', 'Under Maintenance'] as const

export type OperationalStatus = (typeof OPERATIONAL_STATUSES)[number]

export interface EquipmentInput {
  equipment_type: string
  description: string | null
  total_quantity: number | null
  location: string
  operational_status: OperationalStatus | ''
}

export interface EquipmentProblem {
  field: string
  reason: string
}

export class EquipmentRejectedError extends Error {
  readonly problems: EquipmentProblem[]

  constructor(problems: EquipmentProblem[]) {
    super('The equipment entry could not be saved')
    this.name = 'EquipmentRejectedError'
    this.problems = problems
  }
}

function headers(token: string, json = false): HeadersInit {
  return json
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { Authorization: `Bearer ${token}` }
}

function asProblems(detail: unknown): EquipmentProblem[] | null {
  if (!Array.isArray(detail)) return null
  const problems = detail.filter(
    (item): item is EquipmentProblem =>
      typeof item === 'object' &&
      item !== null &&
      typeof (item as EquipmentProblem).field === 'string' &&
      typeof (item as EquipmentProblem).reason === 'string',
  )
  return problems.length === detail.length ? problems : null
}

export async function listEquipment(token: string): Promise<Equipment[]> {
  const response = await fetch('/api/equipment', { headers: headers(token) })
  if (!response.ok) throw new Error(`Could not load the equipment catalogue (${response.status})`)
  return (await response.json()) as Equipment[]
}

export async function createEquipment(token: string, input: EquipmentInput): Promise<Equipment> {
  return saveEquipment('/api/equipment', 'POST', token, input, 201)
}

export async function updateEquipment(
  token: string,
  equipmentId: string,
  input: EquipmentInput,
): Promise<Equipment> {
  return saveEquipment(`/api/equipment/${equipmentId}`, 'PUT', token, input, 200)
}

export async function deactivateEquipment(token: string, equipmentId: string): Promise<Equipment> {
  const response = await fetch(`/api/equipment/${equipmentId}/deactivate`, {
    method: 'POST',
    headers: headers(token),
  })
  if (!response.ok) {
    throw new Error(`The equipment entry could not be deactivated (${response.status})`)
  }
  return (await response.json()) as Equipment
}

async function saveEquipment(
  url: string,
  method: 'POST' | 'PUT',
  token: string,
  input: EquipmentInput,
  successStatus: number,
): Promise<Equipment> {
  const response = await fetch(url, {
    method,
    headers: headers(token, true),
    body: JSON.stringify(input),
  })
  if (response.status === 422) {
    const problems = asProblems(((await response.json()) as { detail: unknown }).detail)
    if (problems !== null) throw new EquipmentRejectedError(problems)
  }
  if (response.status === 409) {
    throw new EquipmentRejectedError([
      { field: 'equipment_type', reason: 'is already recorded at this location' },
    ])
  }
  if (response.status !== successStatus) {
    throw new Error(`The equipment entry could not be saved (${response.status})`)
  }
  return (await response.json()) as Equipment
}

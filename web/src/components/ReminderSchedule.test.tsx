import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import ReminderSchedule from './ReminderSchedule'

// SCRUM-85: the Coordinator's own reminders about work still outstanding.
//
// The rules stay on the API: what a valid lead time is, and what counts as outstanding
// when an occurrence falls due, are its answers. These tests check that the schedule is
// sent whole (AC1 refuses it whole, so a partial send would be meaningless), that a
// refusal names the entry at fault, and that an occurrence already sent reads as sent.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const EVENT = { id: 'event-1', name: 'Orientation Day' } as EventRequest

function reminder(leadMinutes: number, processedAt: string | null = null) {
  return {
    id: `reminder-${leadMinutes}`,
    event_request_id: 'event-1',
    lead_minutes: leadMinutes,
    processed_at: processedAt,
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderSchedule(
  existing: unknown[] = [],
  handler?: (key: string, init?: RequestInit) => Response | undefined,
) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const answer = handler?.(key, init)
    if (answer) return answer
    if (key === 'GET /api/event-requests/event-1/reminders') return json(existing)
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ReminderSchedule event={EVENT} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

function bodyOf(spy: ReturnType<typeof renderSchedule>): unknown {
  const call = spy.mock.calls.find(([, init]) => init?.method === 'PUT')
  return JSON.parse(String(call?.[1]?.body))
}

test('an empty schedule says so rather than looking broken', async () => {
  renderSchedule()

  expect(await screen.findByText('No reminders set.')).toBeInTheDocument()
})

test('lead times are shown in words rather than raw minutes', async () => {
  renderSchedule([reminder(60), reminder(1440), reminder(10080), reminder(45)])

  expect(await screen.findByText('1 hour before')).toBeInTheDocument()
  expect(screen.getByText('1 day before')).toBeInTheDocument()
  expect(screen.getByText('1 week before')).toBeInTheDocument()
  expect(screen.getByText('45 minutes before')).toBeInTheDocument()
})

test('an occurrence already sent reads as sent', async () => {
  // Otherwise a reminder that has fired is indistinguishable from one never set.
  renderSchedule([reminder(60, '2030-01-01T00:00:00Z'), reminder(1440)])

  expect(await screen.findByText('Already sent')).toBeInTheDocument()
})

test('adding a common lead time sends the whole schedule', async () => {
  // AC1 refuses a schedule whole, so the client sends it whole rather than a delta.
  const spy = renderSchedule([reminder(60)], (key) =>
    key === 'PUT /api/event-requests/event-1/reminders'
      ? json([reminder(60), reminder(1440)])
      : undefined,
  )

  // Wait for the existing schedule: the controls stay disabled until it is known, so
  // that a click landing early cannot send a list built from no reminders.
  await screen.findByText('1 hour before')
  const add = screen.getByRole('button', { name: 'Add 1 day before' })
  await waitFor(() => expect(add).toBeEnabled())
  fireEvent.click(add)

  await waitFor(() => expect(bodyOf(spy)).toEqual({ lead_minutes: [60, 1440] }))
})

test('a lead time already set is not offered again', async () => {
  renderSchedule([reminder(1440)])

  await screen.findByText('1 day before')
  expect(screen.queryByRole('button', { name: 'Add 1 day before' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add 1 hour before' })).toBeInTheDocument()
})

test('removing a reminder sends what is left', async () => {
  const spy = renderSchedule([reminder(60), reminder(1440)], (key) =>
    key === 'PUT /api/event-requests/event-1/reminders' ? json([reminder(1440)]) : undefined,
  )

  const remove = await screen.findByLabelText(
    'Remove the 1 hour before reminder for Orientation Day',
  )
  await waitFor(() => expect(remove).toBeEnabled())
  fireEvent.click(remove)

  await waitFor(() => expect(bodyOf(spy)).toEqual({ lead_minutes: [1440] }))
})

test('a custom lead time in minutes is sent as a number', async () => {
  const spy = renderSchedule([], (key) =>
    key === 'PUT /api/event-requests/event-1/reminders' ? json([reminder(90)]) : undefined,
  )

  await screen.findByText('No reminders set.')
  fireEvent.change(screen.getByLabelText('Minutes before Orientation Day to remind me'), {
    target: { value: '90' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))

  await waitFor(() => expect(bodyOf(spy)).toEqual({ lead_minutes: [90] }))
})

test('a refused schedule names what was wrong with it', async () => {
  // AC1: refused whole, so the Coordinator needs to know which entry to fix.
  renderSchedule([], (key) =>
    key === 'PUT /api/event-requests/event-1/reminders'
      ? json({ detail: [{ field: 'lead_minutes', reason: 'must be more than zero minutes' }] }, 422)
      : undefined,
  )

  await screen.findByText('No reminders set.')
  fireEvent.change(screen.getByLabelText('Minutes before Orientation Day to remind me'), {
    target: { value: '0' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add reminder' }))

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent('That reminder schedule was not saved.')
  })
  expect(screen.getByRole('alert')).toHaveTextContent('must be more than zero minutes')
})

test('a schedule that cannot be loaded is reported', async () => {
  renderSchedule([], (key) =>
    key === 'GET /api/event-requests/event-1/reminders' ? json({ detail: 'nope' }, 500) : undefined,
  )

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not load the reminder schedule (500)',
  )
})

test('nothing can be sent before the existing schedule is known', async () => {
  // The API replaces the whole schedule, so a click landing while it was still loading
  // would send a list built from no reminders and wipe what was already there.
  let release: (value: Response) => void = () => {}
  const pending = new Promise<Response>((resolve) => {
    release = resolve
  })
  renderSchedule([], (key) =>
    key === 'GET /api/event-requests/event-1/reminders'
      ? (pending as unknown as Response)
      : undefined,
  )

  const add = await screen.findByRole('button', { name: 'Add 1 hour before' })
  expect(add).toBeDisabled()

  release(json([reminder(1440)]))
  await waitFor(() => expect(add).toBeEnabled())
})

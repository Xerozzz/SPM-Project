import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import ChangeRequestList from './ChangeRequestList'
import MyEventRequests from './MyEventRequests'

// SCRUM-37: the owning Organiser proposes significant changes after submission, and the
// assigned Coordinator sees each proposed value next to the current one.

const summary = {
  id: 'req-1',
  name: 'Orientation Day',
  status: 'approved',
  status_permits: [],
  rejection_reason: null,
}

const plan = {
  event: {
    start_at: '2026-12-01T01:00:00Z',
    end_at: '2026-12-01T05:00:00Z',
    expected_attendance: 100,
    venue_requirement: 'Hall A',
    accessibility_requirement: 'Step-free access',
    layout_requirement: 'Theatre',
  },
  sessions: [],
  equipment: [
    { id: 'e-1', equipment_type: 'Projector', quantity: 2, technical_requirements: null },
  ],
  venue_options: ['Hall A', 'Hall B'],
  equipment_types: ['Projector'],
}

const created = {
  id: 'cr-1',
  event_request_id: 'req-1',
  requested_by_id: 'user-1',
  reason: 'More people signed up',
  status: 'pending',
  event_updated_at: '2026-10-01T00:00:00Z',
  created_at: '2026-10-20T01:00:00Z',
  items: [
    {
      target: 'event',
      target_id: null,
      field: 'expected_attendance',
      current_value: 100,
      proposed_value: 150,
    },
  ],
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Post = (body: Record<string, unknown>) => Response

function renderOrganiser(post: Post, requests: unknown[] = [summary]) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['organiser'] }),
  )
  let listed: unknown[] = []
  const posted: Record<string, unknown>[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests') return json(requests)
    if (key === 'GET /api/event-requests/req-1/change-requests/plan') return json(plan)
    if (key === 'GET /api/event-requests/req-1/change-requests') return json(listed)
    if (key === 'POST /api/event-requests/req-1/change-requests') {
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>
      posted.push(body)
      const response = post(body)
      if (response.ok) listed = [created]
      return response
    }
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MyEventRequests />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return posted
}

async function openForm() {
  fireEvent.click(
    await screen.findByRole('button', { name: 'Propose a change to Orientation Day' }),
  )
  return screen.findByRole('form', { name: 'Propose a change' })
}

describe('SCRUM-37 propose a significant change', () => {
  test('AC1, AC3, AC5: sends only what changed and lists it next to the current value', async () => {
    const posted = renderOrganiser(() => json(created, 201))
    const form = await openForm()

    fireEvent.change(within(form).getByLabelText('Attendance'), { target: { value: '150' } })
    fireEvent.change(within(form).getByLabelText('Reason for the change'), {
      target: { value: 'More people signed up' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send change request' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'your event stays as it is until then',
    )
    expect(posted).toHaveLength(1)
    expect(posted[0]).toMatchObject({
      reason: 'More people signed up',
      event: { expected_attendance: 150 },
      sessions: [],
      equipment: [],
    })
    expect(typeof posted[0].submission_key).toBe('string')
    const list = await screen.findByRole('region', { name: 'Change requests' })
    expect(within(list).getByText('Pending review')).toBeInTheDocument()
    const row = within(list).getByText('Attendance').closest('tr') as HTMLElement
    expect(within(row).getByText('100')).toBeInTheDocument()
    expect(within(row).getByText('150')).toBeInTheDocument()
  })

  test('AC4: a refused proposal lists what to correct', async () => {
    renderOrganiser(() =>
      json(
        {
          detail: [
            { field: 'event.expected_attendance', reason: 'must be a positive whole number' },
          ],
        },
        422,
      ),
    )
    const form = await openForm()

    fireEvent.change(within(form).getByLabelText('Attendance'), { target: { value: '0' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Send change request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'event.expected_attendance must be a positive whole number',
    )
    expect(screen.queryByRole('region', { name: 'Change requests' })).not.toBeInTheDocument()
  })

  test('AC8: a retry after a failure reuses the same submission key', async () => {
    let calls = 0
    const posted = renderOrganiser(() => (++calls === 1 ? json({}, 503) : json(created, 200)))
    const form = await openForm()
    fireEvent.change(within(form).getByLabelText('Attendance'), { target: { value: '150' } })
    fireEvent.change(within(form).getByLabelText('Reason for the change'), {
      target: { value: 'More people' },
    })

    fireEvent.click(within(form).getByRole('button', { name: 'Send change request' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('You can try again safely')
    fireEvent.click(within(form).getByRole('button', { name: 'Send change request' }))

    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(posted).toHaveLength(2)
    expect(posted[1].submission_key).toBe(posted[0].submission_key)
  })

  test('AC7: a rejected request explains the edit and resubmit path instead', async () => {
    renderOrganiser(
      () => json(created),
      [{ ...summary, status: 'rejected', status_permits: ['edit'], rejection_reason: 'Too big' }],
    )

    expect(
      await screen.findByText('To change this request, edit it and submit it again.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Propose a change/ })).not.toBeInTheDocument()
  })
})

test('SCRUM-37 AC6: the coordinator sees equipment and date changes in plain words', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
    json([
      {
        ...created,
        items: [
          {
            target: 'equipment',
            target_id: null,
            field: 'add',
            current_value: null,
            proposed_value: { equipment_type: 'Microphone', quantity: 4 },
          },
          {
            target: 'session',
            target_id: 's-1',
            field: 'session_label',
            current_value: 'Keynote',
            proposed_value: 'Opening',
          },
        ],
      },
    ]),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ChangeRequestList eventId="req-1" />
      </AuthProvider>
    </QueryClientProvider>,
  )

  expect(await screen.findByText('Microphone x 4')).toBeInTheDocument()
  expect(screen.getByText('Equipment add')).toBeInTheDocument()
  expect(screen.getByText('Session name')).toBeInTheDocument()
  expect(screen.getByText('More people signed up')).toBeInTheDocument()
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { Venue } from '../api/venues'
import { AuthProvider } from '../auth/context'
import VenueUnavailabilityManager from './VenueUnavailabilityManager'

// SCRUM-81: a closure over live bookings is recorded, and Venue Staff see what it hits.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'staff-1', roles: ['venue_staff'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const venue = { id: 'venue-1', name: 'Hall A', is_active: true } as unknown as Venue

const saved = {
  id: 'closure-1',
  venue_id: 'venue-1',
  starts_at: '2030-01-01T02:00:00Z',
  ends_at: '2030-01-01T06:00:00Z',
  reason: 'Burst pipe',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderAndSave(affected: unknown[]) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (init?.method === 'POST') return json({ ...saved, affected }, 201)
    expect(String(input)).toBe('/api/venues/venue-1/unavailabilities')
    return json([])
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueUnavailabilityManager venues={[venue]} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  fireEvent.change(screen.getByLabelText('Venue'), { target: { value: venue.id } })
  fireEvent.change(screen.getByLabelText('Start date and time'), {
    target: { value: '2030-01-01T10:00' },
  })
  fireEvent.change(screen.getByLabelText('End date and time'), {
    target: { value: '2030-01-01T14:00' },
  })
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Burst pipe' } })
  fireEvent.click(screen.getByRole('button', { name: 'Record unavailability' }))
}

describe('SCRUM-81 closure impact', () => {
  test('AC1, AC2: a closure over live bookings is saved and lists what it affects', async () => {
    renderAndSave([
      {
        booking_id: 'b-1',
        event_request_id: 'e-1',
        event_name: 'Careers Fair',
        session_label: 'Opening keynote',
        start_at: '2030-01-01T03:00:00Z',
        end_at: '2030-01-01T05:00:00Z',
        status: 'confirmed',
      },
    ])

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('It affects 1 live arrangement')
    expect(status).toHaveTextContent('Nothing was cancelled')
    expect(status).toHaveTextContent('Careers Fair, Opening keynote (confirmed)')
  })

  test('a closure clear of every booking says so', async () => {
    renderAndSave([])

    expect(await screen.findByRole('status')).toHaveTextContent(
      'It does not affect any live booking or hold',
    )
  })
})

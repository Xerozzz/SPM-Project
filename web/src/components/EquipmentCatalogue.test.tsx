import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EquipmentCatalogue from './EquipmentCatalogue'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

function renderCatalogue(fetcher: typeof fetch) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['tech_support'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AuthProvider>
        <EquipmentCatalogue />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('technical support can add equipment and sees it in the catalogue', async () => {
  let posted: Record<string, unknown> = {}
  let saved: Record<string, unknown> | null = null
  renderCatalogue(async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json(saved === null ? [] : [saved])
    posted = JSON.parse(String(init?.body)) as Record<string, unknown>
    saved = { id: 'equipment-1', ...posted }
    return json(saved, 201)
  })

  expect(await screen.findByText('No equipment in the catalogue yet.')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/^Equipment type/), { target: { value: 'Projector' } })
  fireEvent.change(screen.getByLabelText(/^Total quantity/), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText(/^Location/), { target: { value: 'Media Store' } })
  fireEvent.change(screen.getByLabelText(/^Operational status/), {
    target: { value: 'Operational' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add equipment' }))

  await waitFor(() => expect(posted.total_quantity).toBe(4))
  expect(posted.description).toBeNull()
  expect(await screen.findByRole('status')).toHaveTextContent('“Projector” has been added')
  const entry = await screen.findByRole('listitem')
  expect(entry).toHaveTextContent('Equipment type: Projector')
  expect(entry).toHaveTextContent('Description: Not provided')
  expect(entry).toHaveTextContent('Total quantity: 4')
  expect(entry).toHaveTextContent('Location: Media Store')
  expect(entry).toHaveTextContent('Operational status: Operational')
})

test('validation feedback names the equipment field to correct', async () => {
  renderCatalogue(async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    return json({ detail: [{ field: 'total_quantity', reason: 'must be zero or more' }] }, 422)
  })

  await screen.findByText('No equipment in the catalogue yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Add equipment' }))

  expect(await screen.findByText('Total quantity must be zero or more')).toBeInTheDocument()
})

test('technical support can edit an equipment entry and sees the saved values', async () => {
  let saved: Record<string, unknown> = {
    id: 'equipment-1',
    equipment_type: 'Projector',
    description: 'Portable',
    total_quantity: 4,
    location: 'Media Store',
    operational_status: 'Operational',
  }
  let request: { method?: string; url?: string; body?: Record<string, unknown> } = {}
  renderCatalogue(async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([saved])
    request = {
      method: init?.method,
      url: String(input),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
    }
    saved = { id: 'equipment-1', ...request.body }
    return json(saved)
  })

  await screen.findByText('Equipment type:')
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  expect(screen.getByRole('heading', { name: 'Edit equipment' })).toBeInTheDocument()
  expect(screen.getByLabelText(/^Equipment type/)).toHaveValue('Projector')
  fireEvent.change(screen.getByLabelText(/^Total quantity/), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText(/^Operational status/), { target: { value: 'Damaged' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => expect(request.method).toBe('PUT'))
  expect(request.url).toBe('/api/equipment/equipment-1')
  expect(request.body).toMatchObject({ total_quantity: 2, operational_status: 'Damaged' })
  expect(await screen.findByRole('status')).toHaveTextContent('“Projector” has been updated')
  expect(screen.getByRole('listitem')).toHaveTextContent('Total quantity: 2')
  expect(screen.getByRole('listitem')).toHaveTextContent('Operational status: Damaged')
})

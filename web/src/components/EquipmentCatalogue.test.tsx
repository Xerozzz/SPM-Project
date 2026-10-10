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

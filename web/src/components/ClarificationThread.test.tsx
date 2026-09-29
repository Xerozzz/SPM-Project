import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import ClarificationThread from './ClarificationThread'

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

function clarification(id: string, message: string, kind: 'request' | 'response' = 'request') {
  return {
    id,
    event_request_id: 'req-1',
    author_id: 'user-1',
    kind,
    message,
    created_at: '2026-09-17T09:00:00Z',
  }
}

function renderThread(mode: 'coordinator' | 'organiser', fetcher: typeof fetch) {
  localStorage.setItem('connectsphere.token', JSON.stringify({ token: 'token', userId: 'user-1', roles: [mode] }))
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ClarificationThread eventRequestId="req-1" mode={mode} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('coordinator sees history and cannot submit a blank clarification', async () => {
  renderThread('coordinator', async () => json([clarification('msg-1', 'Please clarify layout')]))

  expect(await screen.findByText('Please clarify layout')).toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Request clarification' })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Clarification request'), {
    target: { value: '   ' },
  })
  expect(button).toBeDisabled()
})

test('coordinator submits a clarification through the request endpoint', async () => {
  let postedBody: unknown
  renderThread('coordinator', async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    expect(String(input)).toBe('/api/event-requests/req-1/clarifications')
    postedBody = JSON.parse(String(init?.body)) as unknown
    return json(clarification('msg-1', 'Please clarify layout'), 201)
  })

  fireEvent.change(await screen.findByLabelText('Clarification request'), {
    target: { value: 'Please clarify layout' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Request clarification' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Message sent')
  expect(postedBody).toEqual({ message: 'Please clarify layout' })
})

test('organiser sees persisted history and responds through the response endpoint', async () => {
  let responseUrl = ''
  renderThread('organiser', async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') {
      return json([
        clarification('msg-1', 'Which layout should we use?'),
        clarification('msg-0', 'Earlier answer', 'response'),
      ])
    }
    responseUrl = String(input)
    return json(clarification('msg-2', 'Use classroom layout', 'response'), 201)
  })

  expect(await screen.findByText('Which layout should we use?')).toBeInTheDocument()
  // Each side of the exchange is labelled from `kind`, not guessed from the author.
  expect(screen.getByText('Coordinator asked')).toBeInTheDocument()
  expect(screen.getByText('Organiser replied')).toBeInTheDocument()
  const send = screen.getByRole('button', { name: 'Send response' })
  expect(send).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Response'), { target: { value: '   ' } })
  expect(send).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Response'), {
    target: { value: 'Use classroom layout' },
  })
  fireEvent.click(send)

  await waitFor(() => {
    expect(responseUrl).toBe('/api/event-requests/req-1/clarifications/responses')
  })
  expect(await screen.findByRole('status')).toHaveTextContent('Message sent')
})

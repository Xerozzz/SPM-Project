import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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

function note(id: string, message: string) {
  return {
    id,
    event_request_id: 'req-1',
    author_id: 'user-1',
    kind: 'request',
    message,
    created_at: '2026-09-17T09:00:00Z',
  }
}

function renderThread(fetcher: typeof fetch, canRequest = true) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ClarificationThread eventRequestId="req-1" canRequest={canRequest} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

// TC-106-08: the assigned Coordinator sees internal notes and cannot record a blank one.
test('coordinator sees internal notes and cannot record a blank note', async () => {
  renderThread(async () => json([note('msg-1', 'Called the venue; layout TBC')]))

  expect(await screen.findByText('Internal clarification notes')).toBeInTheDocument()
  expect(await screen.findByText('Called the venue; layout TBC')).toBeInTheDocument()
  expect(screen.getByText('Coordinator note')).toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Record internal note' })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Internal note'), {
    target: { value: '   ' },
  })
  expect(button).toBeDisabled()
})

// TC-106-08: recording posts to the internal-note endpoint, never a response endpoint.
test('coordinator records a note through the internal-note endpoint', async () => {
  let postedUrl = ''
  let postedBody: unknown
  renderThread(async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    postedUrl = String(input)
    postedBody = JSON.parse(String(init?.body)) as unknown
    return json(note('msg-1', 'Called the venue'), 201)
  })

  fireEvent.change(await screen.findByLabelText('Internal note'), {
    target: { value: 'Called the venue' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Record internal note' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Message sent')
  expect(postedUrl).toBe('/api/event-requests/req-1/clarifications')
  expect(postedBody).toEqual({ message: 'Called the venue' })
})

// TC-106-08: without record permission the thread shows notes but no form — there is
// no response control anywhere, because the Organiser surface was removed (SCRUM-106).
test('read-only thread shows notes with no record or response controls', async () => {
  renderThread(async () => json([note('msg-1', 'Called the venue')]), false)

  expect(await screen.findByText('Called the venue')).toBeInTheDocument()
  expect(screen.queryByLabelText('Internal note')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record internal note' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Send response' })).not.toBeInTheDocument()
  expect(screen.queryByText('Organiser replied')).not.toBeInTheDocument()
})

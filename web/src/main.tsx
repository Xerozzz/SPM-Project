import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import './index.css'

// One QueryClient for the whole app. Retries are off so a failing health check shows up
// immediately instead of after three silent retries.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('index.html is missing #root')
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)

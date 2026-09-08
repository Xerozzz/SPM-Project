import { useQuery } from '@tanstack/react-query'

import { getHealth } from './api/client'

/**
 * The scaffold's only page. It exists to prove one thing end to end: the browser can
 * reach FastAPI, which can reach PostgreSQL. Real pages arrive with their own stories.
 */
export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <main className="mx-auto max-w-xl p-8 font-sans">
      <h1 className="text-2xl font-semibold">ConnectSphere</h1>
      <p className="mt-1 text-sm text-slate-500">Event management — development scaffold</p>

      <section className="mt-6 rounded-lg border border-slate-200 p-4">
        <h2 className="font-medium">API health</h2>
        <p className="mt-2 text-sm" role="status">
          {health.isPending && 'Checking the API…'}
          {health.isError && `Cannot reach the API: ${health.error.message}`}
          {health.data && `API and database are ${health.data.status}`}
        </p>
      </section>
    </main>
  )
}

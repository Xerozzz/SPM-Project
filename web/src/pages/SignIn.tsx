import { useState } from 'react'

import { useAuth } from '../auth/useAuth'

/**
 * F1 sign-in page. Shows a generic error that never says whether the account exists.
 */
export default function SignInPage() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await signIn(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#f5f5f5] p-6 sm:p-10">
      <div className="w-full max-w-md">
        <p className="mb-6 text-3xl font-medium tracking-[-0.05em] text-[#202124]">ConnectSphere</p>
        <section className="cs-panel" aria-labelledby="sign-in-title">
          <p className="text-sm font-medium text-slate-500">Welcome back</p>
          <h1 id="sign-in-title" className="mt-2 text-3xl font-medium tracking-[-0.04em] text-[#202124]">
            Sign in
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            Use your supplied ConnectSphere account.
          </p>

          <form onSubmit={onSubmit} className="mt-7 space-y-5">
            <label className="block text-sm font-medium text-slate-700">
              Email
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="cs-field"
              />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Password
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="cs-field"
              />
            </label>
            {error && (
              <p
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {error}
              </p>
            )}
            <button type="submit" disabled={pending} className="cs-button w-full">
              {pending ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </section>
      </div>
    </main>
  )
}

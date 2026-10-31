import { useState } from 'react'

import teamIllustration from '../assets/connectsphere-team-illustration.png'
import { useAuth } from '../auth/useAuth'

/**
 * F1 sign-in page. Shows a generic error that never says whether the account exists.
 */
export default function SignInPage() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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
    <main className="min-h-screen bg-white">
      <div className="grid min-h-screen w-full lg:grid-cols-[1.1fr_1fr]">
        <aside
          aria-label="About ConnectSphere"
          className="hidden overflow-hidden bg-[#eaf7f4] p-10 lg:flex lg:flex-col xl:p-12"
        >
          <p className="text-2xl font-semibold tracking-tight text-slate-950">ConnectSphere</p>
          <div className="mt-16">
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-800">
              Events, connected
            </p>
            <p className="mt-4 max-w-sm text-4xl font-semibold leading-tight tracking-tight text-slate-950">
              Bring every event together.
            </p>
            <p className="mt-5 max-w-sm text-base leading-7 text-slate-600">
              Discover, organise, and take part in events.
            </p>
          </div>
          <div className="relative mt-8 min-h-64 flex-1" aria-hidden="true">
            {/* Offset the asset's transparent left margin to align the artwork with the text. */}
            <img
              src={teamIllustration}
              alt=""
              className="absolute bottom-0 left-0 h-full w-auto max-w-none -translate-x-[37%]"
            />
          </div>
        </aside>
        <section
          className="flex items-center px-6 py-10 sm:px-10 sm:py-14 lg:p-12"
          aria-labelledby="sign-in-title"
        >
          <div className="mx-auto w-full max-w-sm">
            <p className="mb-10 text-xl font-semibold tracking-tight text-slate-950 lg:hidden">
              ConnectSphere
            </p>
            <h1
              id="sign-in-title"
              className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl"
            >
              Welcome back
            </h1>

            <form
              onSubmit={onSubmit}
              aria-busy={pending}
              aria-describedby="sign-in-help"
              className="mt-8 space-y-5"
            >
              <div>
                <label htmlFor="sign-in-email" className="block text-sm font-medium text-slate-700">
                  Email
                </label>
                <input
                  id="sign-in-email"
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="cs-field h-12 border border-slate-300"
                />
              </div>
              <div>
                <label
                  htmlFor="sign-in-password"
                  className="block text-sm font-medium text-slate-700"
                >
                  Password
                </label>
                <div className="relative mt-1">
                  <input
                    id="sign-in-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="cs-field mt-0 h-12 border border-slate-300 pr-32"
                  />
                  <button
                    type="button"
                    aria-controls="sign-in-password"
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-1 right-1 rounded-md px-3 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                  >
                    {showPassword ? 'Hide password' : 'Show password'}
                  </button>
                </div>
              </div>
              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                >
                  {error}
                </p>
              )}
              <button type="submit" disabled={pending} className="cs-button h-12 w-full">
                {pending ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
            <p
              id="sign-in-help"
              className="mt-6 border-t border-slate-100 pt-6 text-sm leading-6 text-slate-500"
            >
              Use the account provided by your organisation.
            </p>
          </div>
        </section>
      </div>
    </main>
  )
}

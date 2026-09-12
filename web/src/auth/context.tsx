import { createContext, useCallback, useContext, useMemo, useState } from 'react'

import { login as apiLogin } from '../api/auth'

interface AuthState {
  token: string | null
  roles: string[]
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
  hasRole: (...allowed: string[]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

const STORAGE_KEY = 'connectsphere.token'

function readStored(): { token: string; roles: string[] } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as { token: string; roles: string[] }
  } catch {
    return null
  }
}

/**
 * Session state for F1 sign-in. The token is stored so a reload keeps the session;
 * sign-out clears it, which invalidates the session client-side (ADR-0005).
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState(readStored)

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await apiLogin(email, password)
    const next = { token: result.access_token, roles: result.roles }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setSession(next)
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setSession(null)
  }, [])

  const hasRole = useCallback(
    (...allowed: string[]) => session?.roles.some((r) => allowed.includes(r)) ?? false,
    [session],
  )

  const value = useMemo<AuthState>(
    () => ({
      token: session?.token ?? null,
      roles: session?.roles ?? [],
      signIn,
      signOut,
      hasRole,
    }),
    [session, signIn, signOut, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}

import { useCallback, useMemo, useState } from 'react'

import { login as apiLogin } from '../api/auth'
import { AuthContext, type AuthState } from './AuthContext'

const STORAGE_KEY = 'connectsphere.token'

type Session = { token: string; userId: string; roles: string[] }

function readStored(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const stored = JSON.parse(raw) as Partial<Session>
    // A session stored before user_id existed has no id. Treat it as signed out rather
    // than as a session with an id that matches nothing, which would silently hide every
    // Approve button instead of prompting a fresh sign-in.
    if (!stored.token || !stored.userId || !stored.roles) return null
    return stored as Session
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
    const next: Session = {
      token: result.access_token,
      userId: result.user_id,
      roles: result.roles,
    }
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
      userId: session?.userId ?? null,
      roles: session?.roles ?? [],
      signIn,
      signOut,
      hasRole,
    }),
    [session, signIn, signOut, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

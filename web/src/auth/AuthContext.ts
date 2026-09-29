import { createContext } from 'react'

export interface AuthState {
  token: string | null
  /** The signed-in user's id, or null when signed out. */
  userId: string | null
  roles: string[]
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
  hasRole: (...allowed: string[]) => boolean
}

/** The session context. Provided by AuthProvider (context.tsx); read with useAuth (useAuth.ts). */
export const AuthContext = createContext<AuthState | null>(null)

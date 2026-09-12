import { useContext } from 'react'

import { AuthContext, type AuthState } from './AuthContext'

/** Read the current session. Throws if used outside AuthProvider, which is always a bug. */
export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}

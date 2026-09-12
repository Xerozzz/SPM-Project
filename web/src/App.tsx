import { AuthProvider } from './auth/context'
import RequireAuth from './auth/RequireAuth'
import HomePage from './pages/Home'

/**
 * F1 shell: unauthenticated users are redirected to sign-in by RequireAuth.
 */
export default function App() {
  return (
    <AuthProvider>
      <RequireAuth>
        <HomePage />
      </RequireAuth>
    </AuthProvider>
  )
}

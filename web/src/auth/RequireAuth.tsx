import { useAuth } from '../auth/context'
import SignInPage from '../pages/SignIn'

/**
 * F1 route guard: unauthenticated users see the sign-in page instead of protected content.
 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  if (!token) return <SignInPage />
  return <>{children}</>
}

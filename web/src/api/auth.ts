/**
 * Auth API calls. Token storage lives in the auth context, not here.
 */

export interface LoginResponse {
  access_token: string
  token_type: string
  /** The signed-in user's id, so the UI can tell "assigned to me" from "assigned to someone else". */
  user_id: string
  roles: string[]
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (response.status === 401) {
    throw new Error('Invalid email or password')
  }
  if (!response.ok) {
    throw new Error(`/api/auth/login responded ${response.status}`)
  }
  return (await response.json()) as LoginResponse
}

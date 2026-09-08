/**
 * The single place the frontend talks to the API.
 *
 * Requests use relative paths: the Vite dev server proxies /api and /health to FastAPI
 * (see vite.config.ts), so the browser never makes a cross-origin request and there is
 * no base URL to configure per environment.
 */

export interface HealthResponse {
  status: string
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`)
  }
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/health')
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = body?.detail ?? JSON.stringify(body)
    } catch {
      msg = (await res.text().catch(() => '')) || msg
    }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

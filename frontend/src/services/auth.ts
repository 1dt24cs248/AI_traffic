import api, { TOKEN_STORAGE_KEY } from './api'
import type { LoginResponse, RegisterRequest, RegisterResponse } from '../types/auth'

// Uses POST /api/auth/token (OAuth2 password flow, form-encoded username/password) —
// per your current backend's Swagger authentication flow, not /api/auth/login.
export async function login(email: string, password: string): Promise<LoginResponse> {
  const formData = new URLSearchParams()
  formData.append('username', email)
  formData.append('password', password)

  const response = await api.post<LoginResponse>('/api/auth/token', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })

  localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token)
  return response.data
}

export async function register(data: RegisterRequest): Promise<RegisterResponse> {
  const response = await api.post<RegisterResponse>('/api/auth/register', data)
  return response.data
}

export function logout(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export function isAuthenticated(): boolean {
  return Boolean(localStorage.getItem(TOKEN_STORAGE_KEY))
}
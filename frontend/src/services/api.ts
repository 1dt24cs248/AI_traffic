import axios from 'axios'

// Note: `as any` avoids needing a vite-env.d.ts ambient-types file that wasn't
// part of Batch 1 — this keeps this batch to exactly the requested files.
const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export const TOKEN_STORAGE_KEY = 'auth_token'

const api = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
    }
    return Promise.reject(error)
  },
)

export default api
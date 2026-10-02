import api from './api'
import type { RouteRequest, RouteResponse } from '../types/routing'

export async function getRoutes(request: RouteRequest): Promise<RouteResponse> {
  const response = await api.post<RouteResponse>('/api/routing/routes', request)
  return response.data
}

export function extractErrorMessage(err: unknown): string {
  const anyErr = err as any
  if (anyErr?.response?.data?.detail) {
    return typeof anyErr.response.data.detail === 'string'
      ? anyErr.response.data.detail
      : JSON.stringify(anyErr.response.data.detail)
  }
  if (anyErr?.response?.status) {
    return `Backend returned status ${anyErr.response.status}.`
  }
  if (err instanceof Error) return err.message
  return 'Unknown error while contacting the backend.'
}
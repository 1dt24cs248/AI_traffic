import api from './api'
import type { AlertFilters, TrafficAlert } from '../types/alerts'

export async function getAlerts(filters: AlertFilters): Promise<TrafficAlert[]> {
  const response = await api.get<TrafficAlert[]>('/api/alerts', { params: filters })
  return response.data
}

export function alertErrorMessage(error: unknown): string {
  if (
    typeof error === 'object'
    && error !== null
    && 'response' in error
    && typeof error.response === 'object'
    && error.response !== null
    && 'data' in error.response
    && typeof error.response.data === 'object'
    && error.response.data !== null
    && 'detail' in error.response.data
    && typeof error.response.data.detail === 'string'
  ) {
    return error.response.data.detail
  }
  if (error instanceof Error) return error.message
  return 'Could not load traffic alerts.'
}

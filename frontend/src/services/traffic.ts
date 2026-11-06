import api from './api'
import type { CurrentTrafficFlow, RouteTrafficResult } from '../types/routing'

export async function getCurrentTrafficFlow(latitude: number, longitude: number) {
  const response = await api.get<CurrentTrafficFlow>('/api/traffic/current-flow', {
    params: { latitude, longitude },
  })
  return response.data
}

export function currentTrafficError(error: unknown): string {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if ((error as any)?.response?.status === 401) return 'Sign in to check current traffic.'
  return 'Current traffic data is unavailable for this road right now.'
}

export async function getRouteTrafficFlow(coordinates: [number, number][], signal?: AbortSignal) {
  const response = await api.post<RouteTrafficResult>('/api/traffic/route-flow', { coordinates }, { signal })
  return response.data
}

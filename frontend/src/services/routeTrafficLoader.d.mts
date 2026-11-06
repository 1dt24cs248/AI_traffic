import type { RouteSummary, RouteTrafficResult } from '../types/routing'

export interface RouteTrafficUiState {
  result: RouteTrafficResult | null
  loading: boolean
  error: string | null
}

export type RouteTrafficStateMap = Record<string, RouteTrafficUiState>
export type RouteTrafficFetcher = (
  coordinates: [number, number][],
  signal?: AbortSignal,
) => Promise<RouteTrafficResult>
export type RouteTrafficPublisher = (state: RouteTrafficStateMap) => void

export function routeTrafficKey(route: RouteSummary): string
export function loadRouteTrafficByRoute(
  routes: RouteSummary[],
  fetchTraffic: RouteTrafficFetcher,
  formatError: (error: unknown) => string,
  publish: RouteTrafficPublisher,
  signal?: AbortSignal,
): Promise<void>

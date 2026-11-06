import type { RouteTrafficResult, RouteWeatherAssessment } from '../types/routing'
export const FUEL_ROUTE_STORAGE_KEY: string
export const FUEL_ROUTE_TTL_MS: number
export function buildFuelImpactRequest(input: {vehicle: string; distanceKm: number; efficiency: number | null; price: number | null; batteryCapacityKwh: number | null; batteryChargePercent: number | null; maxExtraConsumptionPercent: number; traffic: RouteTrafficResult | null; weather: RouteWeatherAssessment | null}): {valid: boolean; errors: string[]; request: Record<string, unknown> | null}
export function saveFuelImpactRoute(storage: Storage, handoff: Record<string, any>): boolean
export function loadFuelImpactRoute(storage: Storage, now?: number): Record<string, any> | null

import api from './api'
import type { RouteTrafficResult, RouteWeatherAssessment } from '../types/routing'
import type { FuelImpactEstimate } from '../types/fuelImpact'
import { buildFuelImpactRequest } from './fuelImpact.mjs'

export async function estimateFuelImpact(input: {
  vehicle: string
  distanceKm: number
  efficiency: number | null
  price: number | null
  batteryCapacityKwh: number | null
  batteryChargePercent: number | null
  maxExtraConsumptionPercent: number
  traffic: RouteTrafficResult | null
  weather: RouteWeatherAssessment | null
}): Promise<FuelImpactEstimate> {
  const result = buildFuelImpactRequest(input)
  if (!result.valid || !result.request) throw new Error(result.errors.join(' '))
  const response = await api.post<FuelImpactEstimate>('/api/simulations/fuel-impact', result.request)
  return response.data
}

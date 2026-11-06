export const FUEL_ROUTE_STORAGE_KEY = 'smartcommute.fuel-impact.route.v1'
export const FUEL_ROUTE_TTL_MS = 2 * 60 * 60 * 1000

export function buildFuelImpactRequest(input) {
  const errors = []
  const number = (value) => value === '' || value === null || value === undefined ? null : Number(value)
  const efficiency = number(input.efficiency)
  const distance = number(input.distanceKm)
  const price = number(input.price)
  const capacity = number(input.batteryCapacityKwh)
  const charge = number(input.batteryChargePercent)
  const sensitivity = number(input.maxExtraConsumptionPercent)
  if (!Number.isFinite(distance) || distance <= 0) errors.push('Enter a route distance greater than zero kilometres.')
  if (!Number.isFinite(efficiency) || efficiency <= 0) errors.push(input.vehicle === 'ev' ? 'Enter efficiency greater than zero kWh per 100 km.' : 'Enter efficiency greater than zero km per litre.')
  if (!Number.isFinite(sensitivity) || sensitivity < 0 || sensitivity > 30) errors.push('Enter a congestion scenario assumption from 0 to 30 percent.')
  if (price !== null && (!Number.isFinite(price) || price <= 0)) errors.push('Price must be greater than zero when supplied.')
  if (capacity !== null && (!Number.isFinite(capacity) || capacity <= 0)) errors.push('Battery capacity must be greater than zero when supplied.')
  if (charge !== null && (!Number.isFinite(charge) || charge < 0 || charge > 100)) errors.push('Battery charge must be between 0 and 100 percent.')
  if (input.vehicle !== 'ev' && (capacity !== null || charge !== null)) errors.push('Battery inputs are only valid for an electric vehicle.')
  if (input.vehicle === 'ev' && charge !== null && capacity === null) errors.push('Battery charge requires a battery capacity.')
  if (errors.length) return { valid: false, errors, request: null }
  return {
    valid: true,
    errors: [],
    request: {
      vehicle: input.vehicle,
      distance_km: distance,
      efficiency,
      price_per_unit: price,
      battery_capacity_kwh: capacity,
      battery_charge_percent: charge,
      max_extra_consumption_percent: sensitivity,
      traffic: input.traffic ?? null,
      weather: input.weather ?? null,
    },
  }
}

export function saveFuelImpactRoute(storage, handoff) {
  if (!handoff || !Number.isFinite(handoff.distanceKm) || handoff.distanceKm <= 0) return false
  try {
    storage.setItem(FUEL_ROUTE_STORAGE_KEY, JSON.stringify({ ...handoff, savedAt: Date.now() }))
    return true
  } catch {
    return false
  }
}

export function loadFuelImpactRoute(storage, now = Date.now()) {
  try {
    const raw = storage.getItem(FUEL_ROUTE_STORAGE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw)
    if (!Number.isFinite(value?.savedAt) || now - value.savedAt > FUEL_ROUTE_TTL_MS || value.savedAt > now || !Number.isFinite(value.distanceKm) || value.distanceKm <= 0) {
      storage.removeItem(FUEL_ROUTE_STORAGE_KEY)
      return null
    }
    return value
  } catch {
    try { storage.removeItem(FUEL_ROUTE_STORAGE_KEY) } catch { /* storage may be disabled */ }
    return null
  }
}

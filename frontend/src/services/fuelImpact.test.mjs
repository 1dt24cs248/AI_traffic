import test from 'node:test'
import assert from 'node:assert/strict'
import { buildFuelImpactRequest, loadFuelImpactRoute, saveFuelImpactRoute } from './fuelImpact.mjs'

const input = (overrides = {}) => ({ vehicle: 'petrol-car', distanceKm: 12.5, efficiency: 14, price: null, batteryCapacityKwh: null, batteryChargePercent: null, maxExtraConsumptionPercent: 15, traffic: null, weather: null, ...overrides })

test('combustion categories create a request using entered units and optional price', () => {
  for (const vehicle of ['petrol-car', 'diesel-car', 'petrol-two-wheeler']) {
    const result = buildFuelImpactRequest(input({ vehicle, efficiency: 18, price: 105 }))
    assert.equal(result.valid, true)
    assert.equal(result.request.vehicle, vehicle)
    assert.equal(result.request.distance_km, 12.5)
    assert.equal(result.request.efficiency, 18)
    assert.equal(result.request.price_per_unit, 105)
    assert.equal(result.request.traffic, null)
  }
})

test('EV request carries kWh efficiency and optional capacity and charge', () => {
  const result = buildFuelImpactRequest(input({ vehicle: 'ev', efficiency: 16.5, price: 8, batteryCapacityKwh: 48, batteryChargePercent: 72 }))
  assert.equal(result.valid, true)
  assert.equal(result.request.efficiency, 16.5)
  assert.equal(result.request.battery_capacity_kwh, 48)
  assert.equal(result.request.battery_charge_percent, 72)
})

test('missing traffic and weather remain explicit nulls without synthetic samples', () => {
  const result = buildFuelImpactRequest(input())
  assert.equal(result.valid, true)
  assert.equal(result.request.traffic, null)
  assert.equal(result.request.weather, null)
})

test('validation identifies missing efficiency, invalid prices, and battery unit errors', () => {
  assert.match(buildFuelImpactRequest(input({ efficiency: null })).errors.join(' '), /efficiency/)
  assert.match(buildFuelImpactRequest(input({ price: 0 })).errors.join(' '), /Price/)
  assert.match(buildFuelImpactRequest(input({ vehicle: 'ev', batteryChargePercent: 50 })).errors.join(' '), /requires a battery capacity/)
  assert.equal(buildFuelImpactRequest(input({ distanceKm: 0 })).valid, false)
  assert.equal(buildFuelImpactRequest(input({ maxExtraConsumptionPercent: 31 })).valid, false)
})

test('route handoff accepts only valid recent route results', () => {
  const values = new Map()
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) }
  assert.equal(saveFuelImpactRoute(storage, { distanceKm: 4.2, traffic: null }), true)
  assert.equal(loadFuelImpactRoute(storage).distanceKm, 4.2)
  assert.equal(loadFuelImpactRoute(storage, Date.now() + 3 * 60 * 60 * 1000), null)
  assert.equal(saveFuelImpactRoute(storage, { distanceKm: 0 }), false)
})

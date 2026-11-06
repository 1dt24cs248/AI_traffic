import assert from 'node:assert/strict'
import { loadRouteTrafficByRoute, routeTrafficKey } from './routeTrafficLoader.mjs'

const route = (coordinates) => ({ geometry: { coordinates } })
const lineA = [[77, 12], [77.01, 12.01]]
const lineB = [[77, 12], [77.02, 12.02]]
const cases = []
const test = (name, run) => cases.push({ name, run })
const result = (status, checked, sampled, points = []) => ({
  status,
  checked_point_count: checked,
  sampled_point_count: sampled,
  points,
  reason: null,
})

function run(routes, fetchTraffic) {
  const updates = []
  return loadRouteTrafficByRoute(
    routes,
    fetchTraffic,
    () => 'Traffic service error',
    (state) => updates.push(state),
  ).then(() => updates)
}

test('loads multi-point traffic for every unique returned route and deduplicates matching geometry', async () => {
  const calls = []
  const updates = await run([route(lineA), route(lineB), route(lineA)], async (coordinates) => {
    calls.push(coordinates)
    return result('available', 5, 5, [{ status: 'available', flow: { current_speed: 32 } }])
  })
  assert.equal(calls.length, 2)
  assert.equal(updates[0][routeTrafficKey(route(lineA))].loading, true)
  assert.equal(updates.at(-1)[routeTrafficKey(route(lineA))].result.checked_point_count, 5)
  assert.equal(updates.at(-1)[routeTrafficKey(route(lineB))].result.points[0].flow.current_speed, 32)
})

test('keeps an unavailable provider result explicit with zero checked points', async () => {
  const updates = await run([route(lineA)], async () => result('unavailable', 0, 5))
  const state = updates.at(-1)[routeTrafficKey(route(lineA))]
  assert.equal(state.loading, false)
  assert.equal(state.error, null)
  assert.equal(state.result.status, 'unavailable')
  assert.equal(state.result.checked_point_count, 0)
})

test('preserves partial coverage and successful point values', async () => {
  const points = [
    { status: 'available', flow: { current_speed: 30, free_flow_speed: 50, confidence: 0.8, road_closure: false, retrieved_at: '2026-10-19T10:00:00Z' } },
    { status: 'unavailable', flow: null, reason: 'No segment' },
  ]
  const updates = await run([route(lineA)], async () => result('partial', 1, 2, points))
  const state = updates.at(-1)[routeTrafficKey(route(lineA))]
  assert.equal(state.result.status, 'partial')
  assert.equal(state.result.checked_point_count, 1)
  assert.equal(state.result.points[0].flow.retrieved_at, '2026-10-19T10:00:00Z')
  assert.equal(state.result.points[1].flow, null)
})

test('transitions from loading to a visible request error', async () => {
  const updates = await run([route(lineA)], async () => { throw new Error('provider unavailable') })
  const state = updates.at(-1)[routeTrafficKey(route(lineA))]
  assert.equal(updates[0][routeTrafficKey(route(lineA))].loading, true)
  assert.equal(state.loading, false)
  assert.equal(state.result, null)
  assert.equal(state.error, 'Traffic service error')
})

test('does not call the provider for route geometry without sampleable coordinates', async () => {
  let calls = 0
  const updates = await run([route([[77, 12]])], async () => { calls += 1 })
  const state = updates.at(-1)[routeTrafficKey(route([[77, 12]]))]
  assert.equal(calls, 0)
  assert.equal(state.loading, false)
  assert.equal(state.result.status, 'unavailable')
  assert.equal(state.result.sampled_point_count, 0)
})

let failures = 0
for (const { name, run: runTest } of cases) {
  try {
    await runTest()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures += 1
    console.error(`FAIL ${name}: ${error?.stack ?? error}`)
  }
}
console.log(`${cases.length - failures}/${cases.length} frontend traffic-flow tests passed`)
if (failures) process.exitCode = 1

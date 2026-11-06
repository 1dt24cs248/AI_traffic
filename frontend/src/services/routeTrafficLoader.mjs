export function routeTrafficKey(route) {
  return JSON.stringify(route?.geometry?.coordinates ?? [])
}

export async function loadRouteTrafficByRoute(routes, fetchTraffic, formatError, publish, signal) {
  const states = {}
  const uniqueRoutes = new Map()

  for (const route of routes) {
    const key = routeTrafficKey(route)
    const coordinates = route?.geometry?.coordinates ?? []
    if (coordinates.length < 2) {
      states[key] = {
        result: { status: 'unavailable', sampled_point_count: 0, checked_point_count: 0, points: [], reason: 'Route geometry does not contain enough coordinates to sample.' },
        loading: false,
        error: null,
      }
      continue
    }
    if (!states[key]) states[key] = { result: null, loading: true, error: null }
    if (!uniqueRoutes.has(key)) uniqueRoutes.set(key, coordinates)
  }

  if (signal?.aborted) return
  publish({ ...states })

  for (const [key, coordinates] of uniqueRoutes) {
    if (signal?.aborted) return
    try {
      const result = await fetchTraffic(coordinates, signal)
      if (signal?.aborted) return
      states[key] = { result, loading: false, error: null }
    } catch (error) {
      if (signal?.aborted) return
      states[key] = { result: null, loading: false, error: formatError(error) }
    }
    publish({ ...states })
  }
}

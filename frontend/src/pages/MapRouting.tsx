import { useCallback, useEffect, useRef, useState } from 'react'
import type React from 'react'
import * as maplibregl from 'maplibre-gl'
import './MapRouting.css'
import MapView from '../components/MapView'
import RouteCard from '../components/RouteCard'
import { useGeolocation } from '../hooks/useGeolocation'
import { getRoutes, extractErrorMessage } from '../services/routing'
import { searchPlaces, extractGeocodingError } from '../services/geocoding'
import type { OriginMode, RouteResponse, GeocodingResult } from '../types/routing'

// Approximate: nearest route VERTEX to the GPS point, not nearest point on a segment.
const DEVIATION_THRESHOLD_METERS = 150
const PLACE_SEARCH_MIN_LENGTH = 2
const PLACE_SEARCH_MAX_RESULTS = 5

const SELECTED_COLOR = '#4f46e5'
const UNSELECTED_COLOR = '#9ca3af'

function sourceId(i: number) {
  return `route-source-${i}`
}
function layerId(i: number) {
  return `route-layer-${i}`
}

function haversineMeters(lng1: number, lat1: number, lng2: number, lat2: number): number {
  const R = 6371000
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function inRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max
}

function MapRouting() {
  const geo = useGeolocation()

  const [originMode, setOriginMode] = useState<OriginMode>('current')
  const [originLat, setOriginLat] = useState('')
  const [originLon, setOriginLon] = useState('')
  const [destLat, setDestLat] = useState('')
  const [destLon, setDestLon] = useState('')
  const [placeQuery, setPlaceQuery] = useState('')
  const [placeResults, setPlaceResults] = useState<GeocodingResult[]>([])
  const [selectedPlace, setSelectedPlace] = useState<GeocodingResult | null>(null)
  const [placeSearchLoading, setPlaceSearchLoading] = useState(false)
  const [placeSearchError, setPlaceSearchError] = useState<string | null>(null)
  const [placeSearched, setPlaceSearched] = useState(false)

  const [map, setMap] = useState<maplibregl.Map | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)

  const [routeResponse, setRouteResponse] = useState<RouteResponse | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)

  const [followMe, setFollowMe] = useState(false)
  const [navigationActive, setNavigationActive] = useState(false)
  const [deviationDetected, setDeviationDetected] = useState(false)

  const currentMarkerRef = useRef<maplibregl.Marker | null>(null)
  const destinationMarkerRef = useRef<maplibregl.Marker | null>(null)
  const drawnRouteCountRef = useRef(0)

  const handleMapReady = useCallback((mapInstance: maplibregl.Map) => {
    setMap(mapInstance)
  }, [])

  const handleMapError = useCallback((message: string) => {
    setMapError(message)
  }, [])

  // Current-location marker: created once, then only its position is updated.
  useEffect(() => {
    if (!map || geo.latitude === null || geo.longitude === null) return
    const lngLat: [number, number] = [geo.longitude, geo.latitude]

    if (!currentMarkerRef.current) {
      currentMarkerRef.current = new maplibregl.Marker({ color: '#2563eb' }).setLngLat(lngLat).addTo(map)
    } else {
      currentMarkerRef.current.setLngLat(lngLat)
    }

    if (followMe) {
      map.panTo(lngLat)
    }
  }, [map, geo.latitude, geo.longitude, followMe])

  // Off-route detection.
  useEffect(() => {
    if (!navigationActive || selectedIndex === null || !routeResponse) return
    if (geo.latitude === null || geo.longitude === null) return

    const coords = routeResponse.routes[selectedIndex]?.geometry?.coordinates
    if (!coords || coords.length === 0) return

    let minDistance = Infinity
    for (const [lng, lat] of coords) {
      const d = haversineMeters(geo.longitude, geo.latitude, lng, lat)
      if (d < minDistance) minDistance = d
    }
    setDeviationDetected(minDistance > DEVIATION_THRESHOLD_METERS)
  }, [navigationActive, selectedIndex, routeResponse, geo.latitude, geo.longitude])

  function removeDrawnRoutes(mapInstance: maplibregl.Map) {
    for (let i = 0; i < drawnRouteCountRef.current; i++) {
      if (mapInstance.getLayer(layerId(i))) mapInstance.removeLayer(layerId(i))
      if (mapInstance.getSource(sourceId(i))) mapInstance.removeSource(sourceId(i))
    }
    drawnRouteCountRef.current = 0
  }

  function drawRoutes(mapInstance: maplibregl.Map, response: RouteResponse, selected: number) {
    removeDrawnRoutes(mapInstance)

    response.routes.forEach((route, i) => {
      mapInstance.addSource(sourceId(i), {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: route.geometry },
      })
      mapInstance.addLayer({
        id: layerId(i),
        type: 'line',
        source: sourceId(i),
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': i === selected ? SELECTED_COLOR : UNSELECTED_COLOR,
          'line-width': i === selected ? 6 : 4,
          'line-opacity': i === selected ? 0.95 : 0.65,
        },
      })
      mapInstance.on('click', layerId(i), () => handleSelectRoute(i))
      mapInstance.on('mouseenter', layerId(i), () => {
        mapInstance.getCanvas().style.cursor = 'pointer'
      })
      mapInstance.on('mouseleave', layerId(i), () => {
        mapInstance.getCanvas().style.cursor = ''
      })
    })
    drawnRouteCountRef.current = response.routes.length
  }

  function restyleSelection(mapInstance: maplibregl.Map, count: number, selected: number) {
    for (let i = 0; i < count; i++) {
      if (!mapInstance.getLayer(layerId(i))) continue
      mapInstance.setPaintProperty(layerId(i), 'line-color', i === selected ? SELECTED_COLOR : UNSELECTED_COLOR)
      mapInstance.setPaintProperty(layerId(i), 'line-width', i === selected ? 6 : 4)
      mapInstance.setPaintProperty(layerId(i), 'line-opacity', i === selected ? 0.95 : 0.65)
    }
  }

  async function handlePlaceSearch(event: React.FormEvent) {
    event.preventDefault()
    if (placeSearchLoading) return

    const trimmed = placeQuery.trim()
    if (trimmed.length < PLACE_SEARCH_MIN_LENGTH) {
      setPlaceSearchError(`Enter at least ${PLACE_SEARCH_MIN_LENGTH} characters to search.`)
      return
    }

    setPlaceSearchLoading(true)
    setPlaceSearchError(null)
    setPlaceSearched(false)
    try {
      const response = await searchPlaces(trimmed)
      setPlaceResults(response.results.slice(0, PLACE_SEARCH_MAX_RESULTS))
      setPlaceSearched(true)
    } catch (err) {
      setPlaceResults([])
      setPlaceSearchError(extractGeocodingError(err))
    } finally {
      setPlaceSearchLoading(false)
    }
  }

  function handlePickPlace(place: GeocodingResult) {
    setSelectedPlace(place)
    setDestLat(String(place.latitude))
    setDestLon(String(place.longitude))
    setPlaceResults([])
    setPlaceSearched(false)
    setPlaceSearchError(null)
  }

  function handleClearPlace() {
    setSelectedPlace(null)
  }

  function handleSelectRoute(index: number) {
    setSelectedIndex(index)
    setDeviationDetected(false)
    if (map) restyleSelection(map, drawnRouteCountRef.current, index)
  }

  async function requestRoutes(originOverride?: { lat: number; lon: number }) {
    if (!map) {
      setRouteError('Map is not ready yet.')
      return
    }

    let oLat: number
    let oLon: number

    if (originOverride) {
      oLat = originOverride.lat
      oLon = originOverride.lon
    } else if (originMode === 'current') {
      if (geo.latitude === null || geo.longitude === null) {
        setRouteError('Current location is not available. Click "Use My Location" and allow access, or switch to manual coordinates.')
        return
      }
      oLat = geo.latitude
      oLon = geo.longitude
    } else {
      oLat = parseFloat(originLat)
      oLon = parseFloat(originLon)
    }

    const dLat = parseFloat(destLat)
    const dLon = parseFloat(destLon)

    if (!inRange(oLat, -90, 90) || !inRange(oLon, -180, 180)) {
      setRouteError('Origin latitude must be between -90 and 90, and longitude between -180 and 180.')
      return
    }
    if (!inRange(dLat, -90, 90) || !inRange(dLon, -180, 180)) {
      setRouteError('Destination latitude must be between -90 and 90, and longitude between -180 and 180.')
      return
    }

    setRouteLoading(true)
    setRouteError(null)
    setDeviationDetected(false)

    try {
      const response = await getRoutes({
        origin_lat: oLat,
        origin_lon: oLon,
        destination_lat: dLat,
        destination_lon: dLon,
        alternatives: true,
        traffic_match_radius_meters: 500,
      })

      if (!response || !Array.isArray(response.routes)) {
        setRouteError('Backend returned a malformed response (no routes array).')
        return
      }
      if (response.routes.length === 0) {
        setRouteError('No route could be found between these coordinates.')
        removeDrawnRoutes(map)
        setRouteResponse(null)
        setSelectedIndex(null)
        return
      }

      setRouteResponse(response)
      setSelectedIndex(0)
      drawRoutes(map, response, 0)

      const destLngLat: [number, number] = [dLon, dLat]
      if (destinationMarkerRef.current) {
        destinationMarkerRef.current.setLngLat(destLngLat)
      } else {
        destinationMarkerRef.current = new maplibregl.Marker({ color: '#dc2626' }).setLngLat(destLngLat).addTo(map)
      }

      const bounds = new maplibregl.LngLatBounds([oLon, oLat], [oLon, oLat])
      bounds.extend(destLngLat)
      response.routes.forEach((route) => {
        route.geometry.coordinates.forEach((c) => bounds.extend(c))
      })
      map.fitBounds(bounds, { padding: 60 })
    } catch (err) {
      setRouteError(extractErrorMessage(err))
    } finally {
      setRouteLoading(false)
    }
  }

  function handleStartNavigation() {
    if (geo.status !== 'active') {
      setRouteError('GPS must be active to start navigation. Click "Use My Location" first.')
      return
    }
    if (selectedIndex === null) {
      setRouteError('Select a route before starting navigation.')
      return
    }
    setRouteError(null)
    setNavigationActive(true)
    setFollowMe(true)
  }

  function handleStopNavigation() {
    setNavigationActive(false)
    setDeviationDetected(false)
  }

  function handleRecalculate() {
    if (geo.latitude === null || geo.longitude === null) {
      setRouteError('Current location is unavailable, cannot recalculate.')
      return
    }
    requestRoutes({ lat: geo.latitude, lon: geo.longitude })
  }

  const locationStatusText: Record<typeof geo.status, string> = {
    idle: 'Location not started',
    requesting: 'Requesting location permission...',
    active: 'Location active',
    denied: 'Location permission denied',
    unavailable: 'Location unavailable',
    unsupported: 'Geolocation is not supported by this browser',
  }

  return (
    <div className="map-routing-page">
      <div className="map-routing-controls">
        <h1 style={{ marginTop: 0 }}>Traffic Route Planner</h1>

        <div style={{ marginBottom: 14 }}>
          <strong>{locationStatusText[geo.status]}</strong>
          {geo.error && <p style={{ color: '#b00020', fontSize: 13, margin: '4px 0' }}>{geo.error}</p>}
          {(geo.status === 'idle' || geo.status === 'denied' || geo.status === 'unavailable') && (
            <div>
              <button onClick={geo.startWatching}>Use My Location</button>
            </div>
          )}
          {geo.status === 'active' && (
            <div>
              <p style={{ fontSize: 12, color: '#666', margin: '4px 0' }}>
                Location accuracy: {geo.accuracy !== null ? `±${Math.round(geo.accuracy)} m` : 'unknown'}
              </p>
              <button onClick={geo.stopWatching}>Stop location tracking</button>
            </div>
          )}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Origin</div>
          <label>
            <input type="radio" checked={originMode === 'current'} onChange={() => setOriginMode('current')} /> Current
            location
          </label>
          <br />
          <label>
            <input type="radio" checked={originMode === 'manual'} onChange={() => setOriginMode('manual')} /> Manual
            coordinates
          </label>
          {originMode === 'manual' && (
            <div style={{ marginTop: 6 }}>
              <input
                type="number"
                step="any"
                placeholder="Origin latitude"
                value={originLat}
                onChange={(e) => setOriginLat(e.target.value)}
                style={{ width: '48%', marginRight: '4%' }}
              />
              <input
                type="number"
                step="any"
                placeholder="Origin longitude"
                value={originLon}
                onChange={(e) => setOriginLon(e.target.value)}
                style={{ width: '48%' }}
              />
            </div>
          )}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Destination — search for a place</div>

          {selectedPlace && (
            <div
              style={{
                padding: 8,
                marginBottom: 8,
                border: '1px solid #c7d2fe',
                backgroundColor: '#eef2ff',
                borderRadius: 6,
                fontSize: 13,
              }}
            >
              <div style={{ fontWeight: 600 }}>Selected destination</div>
              <div>{selectedPlace.display_name}</div>
              <div style={{ color: '#666', fontSize: 12 }}>
                {selectedPlace.latitude.toFixed(5)}, {selectedPlace.longitude.toFixed(5)}
              </div>
              <button type="button" onClick={handleClearPlace} style={{ marginTop: 4 }}>
                Clear
              </button>
            </div>
          )}

          <form onSubmit={handlePlaceSearch}>
            <input
              type="text"
              placeholder="Search a place (e.g. Mysuru, Mysore Palace)"
              value={placeQuery}
              onChange={(e) => setPlaceQuery(e.target.value)}
              maxLength={200}
              style={{ width: '70%', marginRight: '2%' }}
            />
            <button type="submit" disabled={placeSearchLoading} style={{ width: '26%' }}>
              {placeSearchLoading ? 'Searching...' : 'Search'}
            </button>
          </form>

          {placeSearchError && (
            <p style={{ color: '#b00020', fontSize: 13, margin: '6px 0' }}>{placeSearchError}</p>
          )}

          {placeSearched && placeResults.length === 0 && !placeSearchError && (
            <p style={{ color: '#666', fontSize: 13, margin: '6px 0' }}>
              No places found. Try a different or more specific name.
            </p>
          )}

          {placeResults.length > 0 && (
            <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
              {placeResults.map((place, i) => (
                <li key={`${i}-${place.latitude}-${place.longitude}`} style={{ marginBottom: 4 }}>
                  <button
                    type="button"
                    onClick={() => handlePickPlace(place)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: 8,
                      cursor: 'pointer',
                      border: '1px solid #e0e0e0',
                      borderRadius: 6,
                      backgroundColor: '#fff',
                    }}
                  >
                    <div style={{ fontSize: 13 }}>{place.display_name}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p style={{ fontSize: 11, color: '#999', margin: '6px 0 10px' }}>
            Place search via OpenStreetMap Nominatim — this finds locations only and provides no traffic
            information.
          </p>
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Destination (coordinates)</div>
          <input
            type="number"
            step="any"
            placeholder="Destination latitude"
            value={destLat}
            onChange={(e) => setDestLat(e.target.value)}
            style={{ width: '48%', marginRight: '4%' }}
          />
          <input
            type="number"
            step="any"
            placeholder="Destination longitude"
            value={destLon}
            onChange={(e) => setDestLon(e.target.value)}
            style={{ width: '48%' }}
          />
          <p style={{ fontSize: 11, color: '#888', margin: '4px 0 0' }}>
            You can also set the destination manually here — selecting a search result above
            fills these in automatically, and they stay editable either way.
          </p>
        </div>

        <div style={{ marginBottom: 14 }}>
          <button onClick={() => requestRoutes()} disabled={routeLoading}>
            {routeLoading ? 'Loading routes...' : 'Find Routes'}
          </button>
        </div>

        {routeError && <p style={{ color: '#b00020' }}>{routeError}</p>}
        {mapError && <p style={{ color: '#b00020' }}>Map error: {mapError}</p>}

        {routeResponse && (
          <div>
            <h3 style={{ marginBottom: 8 }}>
              Routes ({routeResponse.routes.length}) — provider: {routeResponse.provider}
            </h3>
            {routeResponse.routes.map((route, i) => (
              <RouteCard
                key={i}
                index={i}
                route={route}
                traffic={routeResponse.traffic ?? null}
                isSelected={selectedIndex === i}
                onSelect={() => handleSelectRoute(i)}
              />
            ))}
          </div>
        )}

        {routeResponse && (
          <div style={{ marginTop: 12 }}>
            {!navigationActive ? (
              <button onClick={handleStartNavigation}>Start Navigation</button>
            ) : (
              <button onClick={handleStopNavigation}>Stop Navigation</button>
            )}{' '}
            <label>
              <input type="checkbox" checked={followMe} onChange={(e) => setFollowMe(e.target.checked)} /> Follow Me
            </label>
            <p style={{ fontSize: 12, color: '#555', margin: '6px 0' }}>
              Navigation: {navigationActive ? 'active' : 'inactive'}
            </p>
          </div>
        )}

        {navigationActive && deviationDetected && (
          <div style={{ marginTop: 10, padding: 10, backgroundColor: '#fff3cd', borderRadius: 6 }}>
            <p style={{ margin: '0 0 6px', fontWeight: 600 }}>Route deviation detected</p>
            <p style={{ margin: '0 0 6px', fontSize: 12 }}>
              Position is more than {DEVIATION_THRESHOLD_METERS} m from the selected route (approximate check).
            </p>
            <button onClick={handleRecalculate}>Recalculate Route</button>
          </div>
        )}

        <p style={{ fontSize: 11, color: '#999', marginTop: 20 }}>
          Route distance/duration comes from OSRM routing, not live traffic and not our ML prediction. Map data ©
          OpenStreetMap contributors, tiles © OpenFreeMap.
        </p>
      </div>

      <div className="map-routing-map">
        <MapView onMapReady={handleMapReady} onLoadError={handleMapError} />
      </div>
    </div>
  )
}

export default MapRouting
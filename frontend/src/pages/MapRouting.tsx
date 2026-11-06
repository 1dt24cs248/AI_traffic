import { useCallback, useEffect, useRef, useState } from 'react'
import type React from 'react'
import * as maplibregl from 'maplibre-gl'
import './MapRouting.css'
import MapView from '../components/MapView'
import RouteCard from '../components/RouteCard'
import { useGeolocation } from '../hooks/useGeolocation'
import { getRoutes, extractErrorMessage } from '../services/routing'
import { currentTrafficError, getRouteTrafficFlow } from '../services/traffic'
import { createIncident, extractIncidentError, getIncidents } from '../services/incidents'
import { searchPlaces, reverseGeocode, extractGeocodingError } from '../services/geocoding'
import type { RouteTrafficResult, RouteRequest, RouteResponse, GeocodingResult, VehicleType } from '../types/routing'
import type {
  Incident,
  IncidentCreate,
  IncidentSeverity,
  IncidentType,
} from '../types/incidents'

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

function routeColor(feasible: boolean | undefined, selected: boolean): string {
  if (feasible === false) return '#dc2626'
  return selected ? SELECTED_COLOR : UNSELECTED_COLOR
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

function createIncidentPopup(incident: Incident): HTMLElement {
  const content = document.createElement('div')
  const title = document.createElement('strong')
  const provenance = document.createElement('div')
  const details = document.createElement('div')
  const simulated = incident.source === 'simulation' || incident.source === 'demo'

  title.textContent = incident.type.replace(/_/g, ' ')
  const statusText = incident.status === 'resolved'
    ? 'Resolved'
    : incident.status === 'rejected'
      ? 'Rejected'
    : incident.status === 'verified' || incident.verified
      ? 'Verified'
      : 'Reported — not yet verified'
  provenance.textContent = `${statusText}${simulated ? ' · simulated/demo' : ''}`
  details.textContent = incident.description ?? 'No description provided.'
  content.append(title, provenance, details)
  return content
}

function MapRouting() {
  const geo = useGeolocation()

  const [originMode, setOriginMode] = useState<'place' | 'current'>('place')
  const [originQuery, setOriginQuery] = useState('')
  const [originResults, setOriginResults] = useState<GeocodingResult[]>([])
  const [originPlace, setOriginPlace] = useState<GeocodingResult | null>(null)
  const [originSearchLoading, setOriginSearchLoading] = useState(false)
  const [originSearchError, setOriginSearchError] = useState<string | null>(null)
  const [originSearched, setOriginSearched] = useState(false)
  const [currentLocationLabel, setCurrentLocationLabel] = useState<string | null>(null)
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
  const [routeResultsStale, setRouteResultsStale] = useState(false)
  const [currentFlow, setCurrentFlow] = useState<RouteTrafficResult | null>(null)
  const [currentFlowLoading, setCurrentFlowLoading] = useState(false)
  const [currentFlowError, setCurrentFlowError] = useState<string | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [incidentsLoading, setIncidentsLoading] = useState(true)
  const [incidentsError, setIncidentsError] = useState<string | null>(null)
  const [incidentType, setIncidentType] = useState<IncidentType>('accident')
  const [incidentSeverity, setIncidentSeverity] = useState<IncidentSeverity>('medium')
  const [incidentLat, setIncidentLat] = useState('')
  const [incidentLon, setIncidentLon] = useState('')
  const [incidentRoad, setIncidentRoad] = useState('')
  const [incidentDescription, setIncidentDescription] = useState('')
  const [incidentNotice, setIncidentNotice] = useState<string | null>(null)
  const [incidentFormError, setIncidentFormError] = useState<string | null>(null)
  const [incidentSubmitting, setIncidentSubmitting] = useState(false)
  const [vehicleType, setVehicleType] = useState<VehicleType>('car')
  const [routePreference, setRoutePreference] = useState<'fastest' | 'shortest'>('fastest')

  const [followMe, setFollowMe] = useState(false)
  const [navigationActive, setNavigationActive] = useState(false)
  const [deviationDetected, setDeviationDetected] = useState(false)

  const currentMarkerRef = useRef<maplibregl.Marker | null>(null)
  const destinationMarkerRef = useRef<maplibregl.Marker | null>(null)
  const drawnRouteCountRef = useRef(0)
  const incidentMarkersRef = useRef<maplibregl.Marker[]>([])
  const routeHandlersRef = useRef<
    Record<number, { click: () => void; enter: () => void; leave: () => void }>
  >({})
  const lastRouteRequestRef = useRef<RouteRequest | null>(null)
  const activeRoutePreference = lastRouteRequestRef.current?.route_preference ?? routePreference

  useEffect(() => {
    const route = selectedIndex === null ? null : routeResponse?.routes[selectedIndex]
    const coordinates = route?.geometry.coordinates
    if (!coordinates?.length) {
      setCurrentFlow(null)
      setCurrentFlowError(null)
      setCurrentFlowLoading(false)
      return
    }

    let active = true
    setCurrentFlow(null)
    setCurrentFlowError(null)
    setCurrentFlowLoading(true)
    getRouteTrafficFlow(coordinates)
      .then((flow) => { if (active) setCurrentFlow(flow) })
      .catch((error) => { if (active) setCurrentFlowError(currentTrafficError(error)) })
      .finally(() => { if (active) setCurrentFlowLoading(false) })
    return () => { active = false }
  }, [routeResponse, selectedIndex])

  async function loadIncidents() {
    setIncidentsLoading(true)
    setIncidentsError(null)
    try {
      setIncidents(await getIncidents(undefined, true))
    } catch (err) {
      setIncidents([])
      setIncidentsError(extractIncidentError(err))
    } finally {
      setIncidentsLoading(false)
    }
  }

  useEffect(() => {
    void loadIncidents()
  }, [])

  useEffect(() => {
    incidentMarkersRef.current.forEach((marker) => marker.remove())
    incidentMarkersRef.current = []
    if (!map) return

    incidents.forEach((incident) => {
        const simulated = incident.source === 'simulation' || incident.source === 'demo'
        const marker = new maplibregl.Marker({
          color: incident.status === 'resolved'
            ? '#64748b'
            : simulated
              ? '#7c3aed'
              : incident.status === 'verified' || incident.verified
                ? '#dc2626'
                : '#d97706',
        })
          .setLngLat([incident.longitude, incident.latitude])
          .setPopup(
            new maplibregl.Popup({ offset: 24 }).setDOMContent(
              createIncidentPopup(incident),
            ),
          )
          .addTo(map)
        incidentMarkersRef.current.push(marker)
      })
  }, [map, incidents])

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
      const handlers = routeHandlersRef.current[i]
      if (handlers) {
        mapInstance.off('click', layerId(i), handlers.click)
        mapInstance.off('mouseenter', layerId(i), handlers.enter)
        mapInstance.off('mouseleave', layerId(i), handlers.leave)
        delete routeHandlersRef.current[i]
      }
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
          'line-color': routeColor(route.feasible, i === selected),
          'line-width': i === selected ? 6 : 4,
          'line-opacity': route.feasible === false ? 0.45 : i === selected ? 0.95 : 0.65,
        },
      })
      const click = () => handleSelectRoute(i)
      const enter = () => {
        mapInstance.getCanvas().style.cursor = route.feasible === false ? 'not-allowed' : 'pointer'
      }
      const leave = () => {
        mapInstance.getCanvas().style.cursor = ''
      }
      routeHandlersRef.current[i] = { click, enter, leave }
      mapInstance.on('click', layerId(i), click)
      mapInstance.on('mouseenter', layerId(i), enter)
      mapInstance.on('mouseleave', layerId(i), leave)
    })
    drawnRouteCountRef.current = response.routes.length
  }

  function restyleSelection(mapInstance: maplibregl.Map, count: number, selected: number) {
    for (let i = 0; i < count; i++) {
      if (!mapInstance.getLayer(layerId(i))) continue
      mapInstance.setPaintProperty(
        layerId(i),
        'line-color',
        routeColor(routeResponse?.routes[i]?.feasible, i === selected),
      )
      mapInstance.setPaintProperty(layerId(i), 'line-width', i === selected ? 6 : 4)
      mapInstance.setPaintProperty(
        layerId(i),
        'line-opacity',
        routeResponse?.routes[i]?.feasible === false ? 0.45 : i === selected ? 0.95 : 0.65,
      )
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

  async function handleOriginSearch(event: React.FormEvent) {
    event.preventDefault()
    if (originSearchLoading) return
    const trimmed = originQuery.trim()
    if (trimmed.length < PLACE_SEARCH_MIN_LENGTH) {
      setOriginSearchError(`Enter at least ${PLACE_SEARCH_MIN_LENGTH} characters to search.`)
      return
    }
    setOriginSearchLoading(true)
    setOriginSearchError(null)
    setOriginSearched(false)
    try {
      const response = await searchPlaces(trimmed)
      setOriginResults(response.results.slice(0, PLACE_SEARCH_MAX_RESULTS))
      setOriginSearched(true)
    } catch (err) {
      setOriginResults([])
      setOriginSearchError(extractGeocodingError(err))
    } finally {
      setOriginSearchLoading(false)
    }
  }

  function handlePickOrigin(place: GeocodingResult) {
    setOriginPlace(place)
    setOriginMode('place')
    setOriginResults([])
    setOriginSearched(false)
    setOriginSearchError(null)
  }

  async function handleUseCurrentLocation() {
    setOriginMode('current')
    setOriginPlace(null)
    setCurrentLocationLabel(null)
    const position = await geo.getCurrentLocation()
    if (!position) return
    try {
      const label = await reverseGeocode(position.latitude, position.longitude)
      setCurrentLocationLabel(label ?? 'Current location (address unavailable)')
    } catch {
      setCurrentLocationLabel('Current location (address unavailable)')
    }
  }

  async function handleIncidentSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (incidentSubmitting) return
    const latitude = Number(incidentLat)
    const longitude = Number(incidentLon)
    if (!inRange(latitude, -90, 90) || !inRange(longitude, -180, 180)) {
      setIncidentFormError('Enter valid latitude and longitude before submitting a report.')
      return
    }

    const payload: IncidentCreate = {
      type: incidentType,
      latitude,
      longitude,
      severity: incidentSeverity,
      road_reference: incidentRoad.trim() || undefined,
      description: incidentDescription.trim() || undefined,
    }
    setIncidentNotice(null)
    setIncidentFormError(null)
    setIncidentSubmitting(true)
    try {
      const created = await createIncident(payload)
      setIncidents((previous) => [created, ...previous.filter((item) => item.id !== created.id)])
      setIncidentNotice('Report submitted and pending verification. Track its status in Reports.')
      setIncidentDescription('')
      await loadIncidents()
      if (lastRouteRequestRef.current) {
        await requestRoutes(undefined, true)
      }
    } catch (err) {
      setIncidentFormError(extractIncidentError(err))
    } finally {
      setIncidentSubmitting(false)
    }
  }

  function useCurrentLocationForIncident() {
    if (geo.latitude === null || geo.longitude === null) {
      setIncidentFormError('Current location is unavailable. Enter coordinates manually.')
      return
    }
    setIncidentLat(String(geo.latitude))
    setIncidentLon(String(geo.longitude))
    setIncidentFormError(null)
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
    setDestLat('')
    setDestLon('')
  }

  function handleSelectRoute(index: number) {
    if (!routeResponse?.routes[index]?.feasible) return
    setSelectedIndex(index)
    setDeviationDetected(false)
    if (map) restyleSelection(map, drawnRouteCountRef.current, index)
  }

  async function requestRoutes(
    originOverride?: { lat: number; lon: number },
    refresh = false,
  ) {
    if (!refresh) {
      if (map) removeDrawnRoutes(map)
      destinationMarkerRef.current?.remove()
      destinationMarkerRef.current = null
      lastRouteRequestRef.current = null
      setRouteResponse(null)
      setSelectedIndex(null)
      setRouteResultsStale(false)
      setCurrentFlow(null)
      setCurrentFlowError(null)
      setCurrentFlowLoading(false)
      setNavigationActive(false)
      setFollowMe(false)
      geo.stopWatching()
    }

    if (!map) {
      setRouteError('Map is not ready yet.')
      return
    }

    let routeRequest: RouteRequest

    if (refresh) {
      if (!lastRouteRequestRef.current) {
        setRouteError('Find a route before refreshing incident impacts.')
        return
      }
      routeRequest = {
        ...lastRouteRequestRef.current,
        previous_recommended_index: routeResponse?.recommended_index ?? null,
        vehicle_type: vehicleType,
        route_preference: routePreference,
      }
    } else {
      let oLat: number
      let oLon: number

      if (originOverride) {
        oLat = originOverride.lat
        oLon = originOverride.lon
      } else if (originMode === 'current') {
        if (geo.latitude === null || geo.longitude === null) {
          setRouteError(geo.error ?? 'Current location is not available. Choose a place or allow location access.')
          return
        }
        oLat = geo.latitude
        oLon = geo.longitude
      } else {
        if (!originPlace) {
          setRouteError('Search for an origin and select a suggested place.')
          return
        }
        oLat = originPlace.latitude
        oLon = originPlace.longitude
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

      routeRequest = {
        origin_lat: oLat,
        origin_lon: oLon,
        destination_lat: dLat,
        destination_lon: dLon,
        alternatives: true,
        traffic_match_radius_meters: 500,
        vehicle_type: vehicleType,
        route_preference: routePreference,
      }
    }

    const preservingPreviousResults = refresh && routeResponse !== null
    setRouteLoading(true)
    setRouteError(null)
    setDeviationDetected(false)
    if (!refresh) setRouteResultsStale(false)
    try {
      const response = await getRoutes(routeRequest, refresh)

      if (!response || !Array.isArray(response.routes)) {
        const message = 'Backend returned a malformed response (no routes array).'
        setRouteError(
          preservingPreviousResults
            ? `Refresh failed; showing the previous route results. ${message}`
            : message,
        )
        if (preservingPreviousResults) setRouteResultsStale(true)
        return
      }
      if (response.routes.length === 0) {
        if (preservingPreviousResults) {
          setRouteResultsStale(true)
          setRouteError('Refresh failed; previous route results are stale because no alternatives were returned.')
          return
        }
        setRouteError('No route could be found between these coordinates.')
        removeDrawnRoutes(map)
        setRouteResponse(null)
        setSelectedIndex(null)
        lastRouteRequestRef.current = null
        setNavigationActive(false)
        setFollowMe(false)
        geo.stopWatching()
        return
      }

      lastRouteRequestRef.current = {
        ...routeRequest,
        previous_recommended_index: undefined,
      }
      setRouteResultsStale(false)
      setRouteResponse(response)
      const recommendedIndex = response.recommended_index ?? null
      setSelectedIndex(recommendedIndex)
      drawRoutes(map, response, recommendedIndex ?? -1)
      if (recommendedIndex === null) {
        setNavigationActive(false)
        setFollowMe(false)
        geo.stopWatching()
      }

      const destLngLat: [number, number] = [
        routeRequest.destination_lon,
        routeRequest.destination_lat,
      ]
      if (destinationMarkerRef.current) {
        destinationMarkerRef.current.setLngLat(destLngLat)
      } else {
        destinationMarkerRef.current = new maplibregl.Marker({ color: '#dc2626' }).setLngLat(destLngLat).addTo(map)
      }

      const bounds = new maplibregl.LngLatBounds(
        [routeRequest.origin_lon, routeRequest.origin_lat],
        [routeRequest.origin_lon, routeRequest.origin_lat],
      )
      bounds.extend(destLngLat)
      response.routes.forEach((route) => {
        route.geometry.coordinates.forEach((c) => bounds.extend(c))
      })
      map.fitBounds(bounds, { padding: 60 })
    } catch (err) {
      const message = extractErrorMessage(err)
      setRouteError(
        preservingPreviousResults
          ? `Refresh failed; showing the previous route results. ${message}`
          : message,
      )
      if (preservingPreviousResults) setRouteResultsStale(true)
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
    geo.startWatching()
    setNavigationActive(true)
    setFollowMe(true)
  }

  function handleStopNavigation() {
    setNavigationActive(false)
    setDeviationDetected(false)
    geo.stopWatching()
  }

  function handleRecalculate() {
    if (geo.latitude === null || geo.longitude === null) {
      setRouteError('Current location is unavailable, cannot recalculate.')
      return
    }
    requestRoutes({ lat: geo.latitude, lon: geo.longitude })
  }

  return (
    <div className="map-routing-page">
      <div className="map-routing-controls">
        <h1 style={{ marginTop: 0 }}>Traffic Route Planner</h1>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Origin</div>
          {originMode === 'place' && originPlace && <p role="status">{originPlace.display_name}</p>}
          {originMode === 'current' && geo.latitude !== null && (
            <p role="status">{currentLocationLabel ?? 'Current location selected'}</p>
          )}
          <form onSubmit={handleOriginSearch}>
            <input type="text" aria-label="Origin place" placeholder="Search starting place or address"
              value={originQuery} onChange={(e) => {
                setOriginQuery(e.target.value)
                setOriginPlace(null)
                setOriginMode('place')
              }} maxLength={200}
              style={{ width: '70%', marginRight: '2%' }} />
            <button type="submit" disabled={originSearchLoading} style={{ width: '26%' }}>
              {originSearchLoading ? 'Searching...' : 'Search'}
            </button>
          </form>
          {originSearchError && <p role="alert" style={{ color: '#b00020' }}>{originSearchError}</p>}
          {originSearched && originResults.length === 0 && !originSearchError &&
            <p role="status">No places found. Try a different or more specific name.</p>}
          {originResults.map((place, i) => (
            <button type="button" key={`${i}-${place.latitude}-${place.longitude}`}
              onClick={() => handlePickOrigin(place)} style={{ display: 'block', width: '100%', textAlign: 'left', marginTop: 4 }}>
              {place.display_name}
            </button>
          ))}
          <button type="button" onClick={() => { void handleUseCurrentLocation() }} disabled={geo.loading} style={{ marginTop: 6 }}>
            {geo.loading ? 'Getting location...' : 'Use My Current Location'}
          </button>
          {geo.error && <p role="alert" style={{ color: '#b00020', fontSize: 13 }}>{geo.error}</p>}
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
              onChange={(e) => {
                setPlaceQuery(e.target.value)
                setSelectedPlace(null)
                setDestLat('')
                setDestLon('')
              }}
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
          <label style={{ display: 'block', marginBottom: 8 }}>
            Vehicle type
            <select
              aria-label="Vehicle type"
              value={vehicleType}
              onChange={(event) => setVehicleType(event.target.value as VehicleType)}
              style={{ display: 'block', minWidth: 220, padding: 7, marginTop: 4 }}
            >
              <option value="car">Car</option>
              <option value="motorcycle">Motorcycle (standard driving profile)</option>
              <option value="scooter">Scooter (standard driving profile)</option>
              <option value="bicycle">Bicycle</option>
              <option value="truck">Truck (standard driving profile; restrictions not modeled)</option>
            </select>
          </label>
          <label style={{ display: 'block', marginBottom: 8 }}>
            Route preference
            <select
              aria-label="Route preference"
              value={routePreference}
              onChange={(event) => setRoutePreference(event.target.value as 'fastest' | 'shortest')}
              style={{ display: 'block', minWidth: 220, padding: 7, marginTop: 4 }}
            >
              <option value="fastest">Fastest by OSRM estimate</option>
              <option value="shortest">Shortest by OSRM distance</option>
            </select>
          </label>
          <p style={{ margin: '4px 0', color: '#64748b', fontSize: 12 }}>
            Motorcycle, scooter, and truck use the standard driving profile with limitations; the
            public service does not apply their specific restrictions.
          </p>
          <p style={{ margin: '4px 0 10px', color: '#64748b', fontSize: 12 }}>
            These choices are sent with the next route calculation or refresh.
          </p>
          <button onClick={() => requestRoutes()} disabled={routeLoading}>
            {routeLoading ? 'Loading routes...' : 'Find Routes'}
          </button>
        </div>

        {routeError && <p role="alert" style={{ color: '#b00020' }}>{routeError}</p>}
        {mapError && <p style={{ color: '#b00020' }}>Map error: {mapError}</p>}

        <section style={{ marginTop: 18, borderTop: '1px solid #ddd', paddingTop: 14 }}>
          <h2 style={{ fontSize: 18, margin: '0 0 8px' }}>Road incidents</h2>
          <p style={{ fontSize: 12, color: '#526078' }}>
            Reported (amber) incidents are unverified and do not block routes. Verified (red)
            incidents are reviewed; only confirmed full closures affect route feasibility.
            Resolved (gray) incidents are shown for context.
          </p>
          <button type="button" onClick={() => void loadIncidents()} disabled={incidentsLoading}>
            {incidentsLoading ? 'Loading reports...' : 'Refresh incident reports'}
          </button>
          {incidentsLoading && <p>Loading incident reports...</p>}
          {!incidentsLoading && incidentsError && (
            <p role="alert" style={{ color: '#b00020' }}>
              Incident service unavailable: {incidentsError}
            </p>
          )}
          {!incidentsLoading && !incidentsError && incidents.length === 0 && (
            <p>No incident reports are available.</p>
          )}
          {!incidentsLoading && !incidentsError && incidents.length > 0 && (
            <p style={{ fontSize: 12, color: '#555' }}>
              {incidents.filter((item) => item.status === 'reported').length} reported ·{' '}
              {incidents.filter((item) => item.status === 'verified').length} verified ·{' '}
              {incidents.filter((item) => item.status === 'rejected').length} rejected ·{' '}
              {incidents.filter((item) => item.status === 'resolved').length} resolved ·{' '}
              {incidents.filter((item) => item.source === 'simulation' || item.source === 'demo').length} simulated/demo.
            </p>
          )}

          <form onSubmit={handleIncidentSubmit} style={{ marginTop: 10 }}>
            <strong>Report a hazard</strong>
            <div style={{ marginTop: 6 }}>
              <select
                aria-label="Incident type"
                value={incidentType}
                onChange={(event) => setIncidentType(event.target.value as IncidentType)}
              >
                <option value="accident">Accident</option>
                <option value="road_closure">Road closure</option>
                <option value="fallen_tree">Fallen tree</option>
                <option value="construction">Construction</option>
                <option value="waterlogging">Waterlogging</option>
                <option value="partial_obstruction">Partial obstruction</option>
                <option value="broken_vehicle">Broken vehicle</option>
                <option value="obstruction">Other obstruction</option>
                <option value="other">Other hazard</option>
              </select>
              <select
                aria-label="Incident severity"
                value={incidentSeverity}
                onChange={(event) => setIncidentSeverity(event.target.value as IncidentSeverity)}
                style={{ marginLeft: 6 }}
              >
                <option value="low">Low severity</option>
                <option value="medium">Medium severity</option>
                <option value="high">High severity</option>
                <option value="critical">Critical severity</option>
              </select>
            </div>
            <div style={{ marginTop: 6 }}>
              <input
                type="number"
                step="any"
                aria-label="Incident latitude"
                placeholder="Latitude"
                value={incidentLat}
                onChange={(event) => setIncidentLat(event.target.value)}
                style={{ width: '48%', marginRight: '4%' }}
              />
              <input
                type="number"
                step="any"
                aria-label="Incident longitude"
                placeholder="Longitude"
                value={incidentLon}
                onChange={(event) => setIncidentLon(event.target.value)}
                style={{ width: '48%' }}
              />
            </div>
            <button type="button" onClick={useCurrentLocationForIncident} style={{ marginTop: 6 }}>
              Use current location
            </button>
            <input
              type="text"
              maxLength={255}
              aria-label="Road name or reference"
              placeholder="Road name/reference (optional)"
              value={incidentRoad}
              onChange={(event) => setIncidentRoad(event.target.value)}
              style={{ display: 'block', width: '100%', marginTop: 6 }}
            />
            <textarea
              maxLength={2000}
              aria-label="Incident description"
              placeholder="Description (optional)"
              value={incidentDescription}
              onChange={(event) => setIncidentDescription(event.target.value)}
              style={{ display: 'block', width: '100%', marginTop: 6 }}
            />
            <button type="submit" disabled={incidentSubmitting} style={{ marginTop: 6 }}>
              {incidentSubmitting ? 'Submitting report...' : 'Submit unverified report'}
            </button>
          </form>
          {incidentFormError && (
            <p role="alert" style={{ color: '#b00020' }}>{incidentFormError}</p>
          )}
          {incidentNotice && <p role="status">{incidentNotice}</p>}
        </section>

        {routeResponse && (
          <div>
            {routeResultsStale && (
              <p className="route-stale-banner" role="status">
                Showing previous route results. They are stale because the latest refresh failed.
              </p>
            )}
            <h3 style={{ marginBottom: 8 }}>
              Routes ({routeResponse.routes.length}) — provider: {routeResponse.provider}
            </h3>
            {routeResponse.recommended_index === null && (
              <p role="alert" style={{ color: '#b00020' }}>
                No feasible route is available because every alternative intersects a confirmed closure.
              </p>
            )}
            {routeResponse.ranking_basis && <p>{routeResponse.ranking_basis}</p>}
            <p style={{ fontSize: 12, color: '#64748b' }}>
              Comparison: {routeResponse.comparison_method ?? (
                `${activeRoutePreference === 'fastest' ? 'OSRM duration' : 'OSRM distance'} and verified-closure feasibility`
              )}. OSRM duration is not live-traffic-aware. Local simulated traffic coverage does
              not produce a compatible PEMS08 prediction.
            </p>
            {routeResponse.recommendation_change_reason && (
              <p role="status">{routeResponse.recommendation_change_reason}</p>
            )}
            <button
              type="button"
              onClick={() => {
                void loadIncidents()
                void requestRoutes(undefined, true)
              }}
              disabled={routeLoading}
            >
              {routeLoading ? 'Refreshing routes...' : 'Refresh incidents & route recommendation'}
            </button>
            <p style={{ fontSize: 11, color: '#777' }}>
              Refresh routes and incident reports on demand. No background monitoring is active.
            </p>
            {routeResponse.routes.map((route, i) => (
              <RouteCard
                key={i}
                index={i}
                route={route}
                traffic={routeResponse.traffic ?? null}
                currentFlow={selectedIndex === i ? currentFlow : null}
                currentFlowLoading={selectedIndex === i && currentFlowLoading}
                currentFlowError={selectedIndex === i ? currentFlowError : null}
                isSelected={selectedIndex === i}
                isRecommended={routeResponse.recommended_index === i}
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

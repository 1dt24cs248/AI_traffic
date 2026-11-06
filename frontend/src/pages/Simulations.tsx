import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import RouteCard from '../components/RouteCard'
import FuelImpactEstimator from './FuelImpactEstimator'
import { saveFuelImpactRoute } from '../services/fuelImpact.mjs'
import { currentTrafficError, getRouteTrafficFlow } from '../services/traffic'
import { loadRouteTrafficByRoute, routeTrafficKey, type RouteTrafficStateMap } from '../services/routeTrafficLoader.mjs'
import { searchPlaces, extractGeocodingError } from '../services/geocoding'
import { getRoutes, extractErrorMessage } from '../services/routing'
import {
  createSimulation,
  extractSimulationError,
  getSimulation,
  getSimulations,
} from '../services/simulations'
import type {
  SimulationCreateRequest,
  SimulationRunDetail,
  SimulationRunSummary,
} from '../types/simulations'
import type { GeocodingResult, RouteResponse, VehicleType } from '../types/routing'

function SimulationTools() {
  const [name, setName] = useState('Baseline demo')
  const [duration, setDuration] = useState(120)
  const [interval, setInterval] = useState(5)
  const [seed, setSeed] = useState(42)
  const [startTime, setStartTime] = useState('')
  const [runs, setRuns] = useState<SimulationRunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<SimulationRunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const loadRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRuns(await getSimulations())
    } catch (err) {
      setError(extractSimulationError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCreating(true)
    setError(null)
    setNotice(null)
    try {
      const payload: SimulationCreateRequest = {
        name: name.trim(),
        duration_minutes: duration,
        interval_minutes: interval,
        seed,
        scenario_type: 'baseline',
        ...(startTime ? { start_time: new Date(startTime).toISOString() } : {}),
      }
      const created = await createSimulation(payload)
      setNotice(
        `Completed: ${created.record_count} synthetic observations across ${created.road_count} roads.`,
      )
      setSelectedRun(await getSimulation(created.id))
      await loadRuns()
    } catch (err) {
      setError(extractSimulationError(err))
    } finally {
      setCreating(false)
    }
  }

  async function openRun(runId: string) {
    setError(null)
    try {
      setSelectedRun(await getSimulation(runId))
    } catch (err) {
      setError(extractSimulationError(err))
    }
  }

  return (
    <section>
      <h2>Simulation data lab</h2>
      <p>
        Create reproducible baseline traffic data for development and demonstration.
        This output is synthetic, not live traffic and not an AI prediction.
      </p>
      <p
        role="note"
        style={{
          padding: 10,
          border: '1px solid #d6b46a',
          borderRadius: 6,
          backgroundColor: '#fffaf0',
        }}
      >
        SYNTHETIC / SIMULATED DATA — persisted with source <code>simulation</code>.
        It is never sent to the incompatible PEMS08 prediction model.
      </p>

      <section aria-labelledby="simulation-config-heading">
        <h2 id="simulation-config-heading">Run a baseline simulation</h2>
        <p>
          Generate two hours of synthetic observations for the built-in roads using the default
          five-minute interval. These values are saved as simulation data.
        </p>
        <form onSubmit={handleSubmit}>
          <details>
            <summary>Advanced settings (optional)</summary>
            <label style={{ display: 'block', margin: '10px 0' }}>
              Run name
              <input
                required
                maxLength={255}
                value={name}
                onChange={(event) => setName(event.target.value)}
                style={{ display: 'block', width: 'min(100%, 420px)' }}
              />
            </label>
            <label style={{ display: 'block', marginBottom: 10 }}>
              Duration (minutes, 5–1440)
              <input
                type="number"
                min={5}
                max={1440}
                step={5}
                required
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
              />
            </label>
            <label style={{ display: 'block', marginBottom: 10 }}>
              Interval (minutes, 1–60; must divide duration)
              <input
                type="number"
                min={1}
                max={60}
                required
                value={interval}
                onChange={(event) => setInterval(Number(event.target.value))}
              />
            </label>
            <label style={{ display: 'block', marginBottom: 10 }}>
              Reproducible seed
              <input
                type="number"
                min={0}
                max={4294967295}
                required
                value={seed}
                onChange={(event) => setSeed(Number(event.target.value))}
              />
            </label>
            <label style={{ display: 'block', marginBottom: 10 }}>
              Start time (optional; defaults to backend UTC time)
              <input
                type="datetime-local"
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
              />
            </label>
          </details>
          <button type="submit" disabled={creating}>
            {creating ? 'Generating and saving…' : 'Generate simulation'}
          </button>
        </form>
      </section>

      {error && <p role="alert" style={{ color: '#b00020' }}>{error}</p>}
      {notice && <p role="status">{notice}</p>}

      <section aria-labelledby="simulation-runs-heading" style={{ marginTop: 24 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <h2 id="simulation-runs-heading">Saved simulation runs</h2>
          <button type="button" onClick={() => void loadRuns()} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh runs'}
          </button>
        </div>
        {loading && <p role="status">Loading saved runs…</p>}
        {!loading && runs.length === 0 && <p>No saved simulation runs yet.</p>}
        {runs.length > 0 && (
          <ul>
            {runs.map((run) => (
              <li key={run.id} style={{ marginBottom: 8 }}>
                <button type="button" onClick={() => void openRun(run.id)}>
                  {run.name} — {run.record_count} records, {run.road_count} roads
                </button>
                <span> · SYNTHETIC / SIMULATED · {new Date(run.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedRun && (
        <section aria-labelledby="simulation-detail-heading" style={{ marginTop: 20 }}>
          <h2 id="simulation-detail-heading">{selectedRun.name}</h2>
          <p><strong>Status:</strong> {selectedRun.status} · <strong>Data:</strong> SYNTHETIC / SIMULATED</p>
          <p>
            <strong>Records:</strong> {selectedRun.record_count} · <strong>Roads:</strong>{' '}
            {selectedRun.road_count} · <strong>Scenario:</strong> {selectedRun.scenario_type}
          </p>
          <p>
            <strong>Window:</strong> {new Date(selectedRun.start_time).toLocaleString()} –{' '}
            {new Date(selectedRun.end_time).toLocaleString()} · {selectedRun.duration_minutes} minutes
            at {selectedRun.interval_minutes}-minute intervals
          </p>
          <p><strong>Seed:</strong> {selectedRun.seed}</p>
          <p><strong>Roads:</strong> {selectedRun.road_ids_affected.join(', ')}</p>
          <p>{selectedRun.notes}</p>
          <h3>Generated road summaries</h3>
          <ul>
            {(selectedRun.scenario_snapshot.roads ?? []).map((road) => (
              <li key={road.road_id}>
                {road.road_name} ({road.road_id}): {road.record_count} observations,
                {' '}{road.average_speed_kmh.toFixed(1)} km/h average speed,
                {' '}{road.average_vehicle_count.toFixed(1)} average vehicles
              </li>
            ))}
          </ul>
          <h3>Limitations</h3>
          <ul>
            {(selectedRun.scenario_snapshot.limitations ?? []).map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}

function defaultDepartureValue(): string {
  const departure = new Date(Date.now() + 60 * 60 * 1000)
  departure.setMinutes(Math.ceil(departure.getMinutes() / 15) * 15, 0, 0)
  return new Date(departure.getTime() - departure.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16)
}

export function ScenarioPlanner({ showSimulationTools = true }: { showSimulationTools?: boolean } = {}) {
  const navigate = useNavigate()
  const [origin, setOrigin] = useState<GeocodingResult | null>(null)
  const [destination, setDestination] = useState<GeocodingResult | null>(null)
  const [departure, setDeparture] = useState(defaultDepartureValue)
  const [vehicleType, setVehicleType] = useState<VehicleType>('car')
  const [routePreference, setRoutePreference] = useState<'fastest' | 'shortest'>('fastest')
  const [response, setResponse] = useState<RouteResponse | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [trafficByRoute, setTrafficByRoute] = useState<RouteTrafficStateMap>({})

  useEffect(() => {
    if (!response) {
      setTrafficByRoute({})
      return
    }
    const controller = new AbortController()
    void loadRouteTrafficByRoute(
      response.routes,
      getRouteTrafficFlow,
      currentTrafficError,
      setTrafficByRoute,
      controller.signal,
    )
    return () => controller.abort()
  }, [response])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setResponse(null)
    setSelectedIndex(null)
    if (!origin || !destination) {
      setError('Search for and select both locations before checking the trip.')
      return
    }
    const departureDate = new Date(departure)
    if (Number.isNaN(departureDate.getTime())) {
      setError('Choose a valid departure date and time.')
      return
    }

    setLoading(true)
    try {
      const result = await getRoutes({
        origin_lat: origin.latitude,
        origin_lon: origin.longitude,
        destination_lat: destination.latitude,
        destination_lon: destination.longitude,
        alternatives: true,
        traffic_match_radius_meters: 500,
        vehicle_type: vehicleType,
        route_preference: routePreference,
        departure_datetime: departureDate.toISOString(),
      })
      setResponse(result)
      setSelectedIndex(result.recommended_index ?? result.fastest_index ?? null)
      if (result.routes.length === 0) setError('No route was returned for these locations.')
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="scenario-planner">
      {showSimulationTools && <header className="scenario-hero">
        <p className="eyebrow">COMMUTER ROUTE PLANNER</p>
        <h1>Plan your trip</h1>
        <p>Compare road routes, estimated journey times, forecast weather, and nearby incident reports.</p>
      </header>}

      <section className="scenario-panel" aria-labelledby="trip-form-heading">
        {!showSimulationTools && <p className="trip-step-label">STEP 01 <span>·</span> JOURNEY DETAILS</p>}
        <h2 id="trip-form-heading">Where are you going?</h2>
        <form onSubmit={(event) => void handleSubmit(event)}>
          <div className="scenario-form-grid">
            <PlacePicker
              label="Starting location"
              placeholder="Try Rajajinagar, Bengaluru"
              selected={origin}
              onSelect={setOrigin}
            />
            <PlacePicker
              label="Destination"
              placeholder="Try Majestic, Bengaluru"
              selected={destination}
              onSelect={setDestination}
            />
            <label>
              Travel date and departure time
              <input
                type="datetime-local"
                required
                value={departure}
                onChange={(event) => setDeparture(event.target.value)}
              />
            </label>
            <label>
              Travel mode
              <select value={vehicleType} onChange={(event) => setVehicleType(event.target.value as VehicleType)}>
                <option value="car">Car</option>
                <option value="motorcycle">Motorcycle</option>
                <option value="scooter">Scooter</option>
                <option value="bicycle">Bicycle</option>
                <option value="truck">Truck</option>
              </select>
            </label>
            <label>
              Route preference
              <select value={routePreference} onChange={(event) => setRoutePreference(event.target.value as 'fastest' | 'shortest')}>
                <option value="fastest">Fastest baseline estimate</option>
                <option value="shortest">Shortest route</option>
              </select>
            </label>
          </div>
          <button className="scenario-primary-button" type="submit" disabled={loading || !origin || !destination}>
            {loading ? 'Comparing trip options…' : 'Compare trip options'}
          </button>
          <p className="scenario-help">
            Route time is an OSRM map estimate, not a future congestion forecast. Departure time selects the weather forecast window where available; the app does not calculate an optimal departure time.
          </p>
        </form>
      </section>

      {error && <p role="alert" className="scenario-message scenario-error">{error}</p>}
      {loading && <p role="status" className="scenario-message">Getting route and forecast information…</p>}

      {response && (
        <section className="scenario-results" aria-labelledby="scenario-results-heading">
          <div className="scenario-results-heading">
            <div>
              <p className="eyebrow">{showSimulationTools ? 'TRIP OPTIONS' : 'STEP 02 · ROUTE COMPARISON'}</p>
              <h2 id="scenario-results-heading">{response.routes.length} route{response.routes.length === 1 ? '' : 's'} found</h2>
              <p>{origin?.display_name} → {destination?.display_name}</p>
            </div>
            <div className="scenario-departure">
              Departure<br /><strong>{new Date(departure).toLocaleString()}</strong>
            </div>
          </div>
          {response.ranking_basis && (
            <p className="scenario-method"><strong>How routes are compared:</strong> {response.ranking_basis}</p>
          )}
          {response.routes[0]?.vehicle_profile_note && (
            <p role="note" className="scenario-method">{response.routes[0].vehicle_profile_note}</p>
          )}
          <p role="note" className="scenario-truth-note">
            No validated traffic forecast is available for these Bengaluru roads. Traffic status is shown as unavailable
            unless compatible observations exist; synthetic records are never passed to PEMS08.
          </p>
          <div className="scenario-route-list">
            {response.routes.map((route, index) => (
              <RouteCard
                key={`${route.distance_meters}-${index}`}
                index={index}
                route={route}
                traffic={response.traffic}
                currentFlow={trafficByRoute[routeTrafficKey(route)]?.result}
                currentFlowLoading={trafficByRoute[routeTrafficKey(route)]?.loading ?? Boolean(response)}
                currentFlowError={trafficByRoute[routeTrafficKey(route)]?.error}
                showCurrentTraffic
                isSelected={selectedIndex === index}
                isRecommended={response.recommended_index === index}
                onSelect={() => setSelectedIndex(index)}
                onEstimate={() => {
                  const saved = saveFuelImpactRoute(window.sessionStorage, {
                    label: `Route ${index + 1}${response.recommended_index === index ? ' · Recommended' : ''} · ${origin?.display_name ?? 'Origin'} to ${destination?.display_name ?? 'Destination'}`,
                    distanceKm: route.distance_km,
                    traffic: trafficByRoute[routeTrafficKey(route)]?.result ?? null,
                    weather: route.weather ?? null,
                  })
                  if (!saved) setError('This browser could not carry the selected route into the estimator.')
                  else navigate('/simulations')
                }}
              />
            ))}
          </div>
          <p className="scenario-method">
            Route distances and durations are calculated from OpenStreetMap road data by OSRM. The optional route
            comparison score is rule-based, not a machine-learning traffic prediction. Weather is a provider forecast
            for sampled route points; incident reports are matched geographically and may be incomplete.
          </p>
        </section>
      )}

      {showSimulationTools && <details className="scenario-tools">
        <summary>Advanced synthetic simulation tools</summary>
        <p>Generate and inspect clearly labeled synthetic data for demonstrations. It is not a real traffic forecast.</p>
        <SimulationTools />
      </details>}
    </div>
  )
}

function PlacePicker({
  label,
  placeholder,
  selected,
  onSelect,
}: {
  label: string
  placeholder: string
  selected: GeocodingResult | null
  onSelect: (place: GeocodingResult | null) => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GeocodingResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search() {
    if (query.trim().length < 2) {
      setError('Enter at least two characters to search.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const response = await searchPlaces(query.trim())
      setResults(response.results)
      if (response.results.length === 0) setError('No matching places found. Try adding the city name.')
    } catch (err) {
      setError(extractGeocodingError(err))
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="scenario-place-picker">
      <label>
        {label}
        <span className="scenario-place-search">
          <input
            required
            value={selected?.display_name ?? query}
            placeholder={placeholder}
            onChange={(event) => {
              setQuery(event.target.value)
              setResults([])
              setError(null)
              if (selected) onSelect(null)
            }}
          />
          <button type="button" onClick={() => void search()} disabled={loading || Boolean(selected)}>
            {loading ? 'Searching…' : 'Search'}
          </button>
        </span>
      </label>
      {error && <span className="scenario-field-error" role="alert">{error}</span>}
      {results.length > 0 && (
        <ul className="scenario-place-results" aria-label={`${label} search results`}>
          {results.map((place, index) => (
            <li key={`${place.latitude}-${place.longitude}-${index}`}>
              <button type="button" onClick={() => { onSelect(place); setQuery(place.display_name); setResults([]); setError(null) }}>
                {place.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected && <span className="scenario-selected-place" role="status">Location selected</span>}
    </div>
  )
}

export default function Simulations() {
  return <FuelImpactEstimator />
}

import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { RouteTrafficResult } from '../types/routing'
import { loadFuelImpactRoute } from '../services/fuelImpact.mjs'
import { estimateFuelImpact } from '../services/fuelImpactApi'
import { extractErrorMessage } from '../services/routing'
import type { FuelImpactEstimate } from '../types/fuelImpact'

type Vehicle = 'petrol-car' | 'diesel-car' | 'petrol-two-wheeler' | 'ev'
type Handoff = { distanceKm: number; label?: string; traffic?: RouteTrafficResult | null; weather?: any; savedAt?: number }

function FuelImpactEstimator() {
  const route = useMemo(() => {
    try { return loadFuelImpactRoute(window.sessionStorage) as Handoff | null } catch { return null }
  }, [])
  const [manualDistance, setManualDistance] = useState('')
  const [vehicle, setVehicle] = useState<Vehicle>('petrol-car')
  const [efficiency, setEfficiency] = useState('')
  const [price, setPrice] = useState('')
  const [batteryCapacity, setBatteryCapacity] = useState('')
  const [batteryCharge, setBatteryCharge] = useState('')
  const [sensitivity, setSensitivity] = useState('15')
  const [result, setResult] = useState<FuelImpactEstimate | null>(null)
  const [calculationError, setCalculationError] = useState<string | null>(null)
  const [calculating, setCalculating] = useState(false)
  const distanceKm = route?.distanceKm ?? Number(manualDistance)
  const isEv = vehicle === 'ev'
  const traffic = route?.traffic ?? null
  const weather = route?.weather ?? null
  const unit = isEv ? 'kWh' : 'L'
  function invalidateEstimate() {
    setResult(null)
    setCalculationError(null)
  }
  async function handleCalculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCalculating(true)
    setCalculationError(null)
    setResult(null)
    try {
      setResult(await estimateFuelImpact({
        vehicle,
        distanceKm,
        efficiency: efficiency === '' ? null : Number(efficiency),
        price: price === '' ? null : Number(price),
        batteryCapacityKwh: batteryCapacity === '' ? null : Number(batteryCapacity),
        batteryChargePercent: batteryCharge === '' ? null : Number(batteryCharge),
        maxExtraConsumptionPercent: Number(sensitivity),
        traffic,
        weather,
      }))
    } catch (error) {
      setCalculationError(extractErrorMessage(error))
    } finally {
      setCalculating(false)
    }
  }

  return (
    <div className="fuel-impact-page">
      <header className="fuel-impact-hero">
        <p className="eyebrow">SIMULATIONS · ESTIMATOR</p>
        <h1>Stop-and-Go Fuel &amp; Energy Impact Estimator</h1>
        <p>Explore how sampled current traffic could affect energy use for a route you already planned.</p>
        <p className="fuel-impact-disclosure" role="note">Approximate scenario estimates only. They are not measured consumption or guaranteed savings; sampled traffic does not cover the whole route.</p>
      </header>

      <section className="fuel-impact-panel" aria-labelledby="route-context-heading">
        <h2 id="route-context-heading">Route distance</h2>
        {route ? (
          <div className="fuel-route-context">
            <strong>{route.label ?? 'Route selected from SmartCommute AI'}</strong>
            <span>{route.distanceKm.toFixed(1)} km · OSRM baseline route distance</span>
            <Link to="/predictions">Choose a different route in SmartCommute AI</Link>
          </div>
        ) : (
          <>
            <p>No recent route was transferred. Plan a trip in SmartCommute AI to reuse its route and traffic results, or enter a known distance below.</p>
            <label className="fuel-field">Route distance (km)
            <input type="number" min="0.1" step="0.1" value={manualDistance} onChange={(event) => { setManualDistance(event.target.value); invalidateEstimate() }} placeholder="e.g. 8.5" />
            </label>
            <Link to="/predictions">Plan a trip in SmartCommute AI</Link>
          </>
        )}
        <p className="fuel-small-note">When entered manually, distance is your own assumption. This page does not make a second route request.</p>
      </section>

      <form onSubmit={(event) => void handleCalculate(event)}>
      <section className="fuel-impact-panel" aria-labelledby="vehicle-heading">
        <h2 id="vehicle-heading">Your vehicle assumptions</h2>
        <div className="fuel-form-grid">
          <label className="fuel-field">Vehicle category
            <select value={vehicle} onChange={(event) => { const value = event.target.value as Vehicle; setVehicle(value); if (value !== 'ev') { setBatteryCapacity(''); setBatteryCharge('') }; invalidateEstimate() }}>
              <option value="petrol-car">Petrol car</option>
              <option value="diesel-car">Diesel car</option>
              <option value="petrol-two-wheeler">Petrol two-wheeler</option>
              <option value="ev">Electric vehicle</option>
            </select>
          </label>
          <label className="fuel-field">{isEv ? 'Efficiency (kWh per 100 km)' : 'Efficiency (km per litre)'}
            <input aria-label={isEv ? 'Efficiency kWh per 100 km' : 'Efficiency km per litre'} type="number" min="0.01" step="any" value={efficiency} onChange={(event) => { setEfficiency(event.target.value); invalidateEstimate() }} placeholder={isEv ? 'Example: 16' : 'Example: 14'} />
          </label>
          <label className="fuel-field">{isEv ? 'Electricity price (₹/kWh), optional' : 'Fuel price (₹/litre), optional'}
            <input type="number" min="0.01" step="any" value={price} onChange={(event) => { setPrice(event.target.value); invalidateEstimate() }} placeholder={isEv ? 'Enter your tariff' : 'Enter your local price'} />
          </label>
          {isEv && <>
            <label className="fuel-field">Battery capacity (kWh), optional
              <input type="number" min="0.01" step="any" value={batteryCapacity} onChange={(event) => { setBatteryCapacity(event.target.value); invalidateEstimate() }} placeholder="Example: 40" />
            </label>
            <label className="fuel-field">Current battery charge (%), optional
              <input type="number" min="0" max="100" step="any" value={batteryCharge} onChange={(event) => { setBatteryCharge(event.target.value); invalidateEstimate() }} placeholder="Example: 80" />
            </label>
          </>}
          <label className="fuel-field">Maximum extra-use scenario assumption (%)
            <input type="number" min="0" max="30" step="1" value={sensitivity} onChange={(event) => { setSensitivity(event.target.value); invalidateEstimate() }} />
          </label>
        </div>
          <p className="fuel-small-note">Use your vehicle’s figures where available. Example placeholders are not assumed values; the scenario cap is adjustable and is not calibrated to a specific vehicle.</p>
        <button className="scenario-primary-button" type="submit" disabled={calculating}>{calculating ? 'Calculating estimate…' : 'Calculate estimate'}</button>
      </section>

      <section className="fuel-impact-panel" aria-labelledby="impact-heading" aria-live="polite">
        <h2 id="impact-heading">Estimated fuel &amp; energy impact</h2>
        {calculationError && <p role="alert">{calculationError}</p>}
        {calculating && <p role="status">Calculating an estimate from the selected route and entered vehicle assumptions…</p>}
        {!calculating && !calculationError && !result && <p>Enter your vehicle efficiency and calculate to see a route estimate.</p>}
        {result && <>
          <p className="fuel-result-intro">Your estimate uses the route distance, vehicle efficiency, and the traffic evidence available for this route.</p>
          <div className="fuel-traffic-summary">
            <div><span>Valid traffic samples</span><strong>{result.sample_count > 0 ? result.sample_count : 'Unavailable'}</strong><small>Paired current and free-flow speeds</small></div>
            <div><span>Reduced-speed samples</span><strong>{result.sample_count > 0 ? result.reduced_count : 'Unavailable'}</strong><small>Sample points only</small></div>
            <div><span>Heavy speed reductions</span><strong>{result.sample_count > 0 ? result.heavy_reduction_count : 'Unavailable'}</strong><small>Heuristic speed bands</small></div>
          </div>
          <p className="fuel-small-note">Traffic coverage: {result.traffic_coverage}. A few sampled points cannot show conditions along every part of a route or confirm actual stops.</p>
          <div className="fuel-result-grid">
            <Result label={`Baseline ${isEv ? 'energy' : 'fuel'}`} value={`${result.baseline.toFixed(2)} ${unit}`} detail={`Calculated from ${result.distance_km.toFixed(1)} km and the efficiency you entered. ${isEv ? 'Energy = distance × kWh per 100 km ÷ 100.' : 'Fuel = distance ÷ kilometres per litre.'}`} />
            <Result label={`Additional estimated ${isEv ? 'energy' : 'fuel'}`} value={result.additional === null ? 'Unavailable' : `${result.additional.toFixed(2)} ${unit}`} detail={`Scenario estimate based on valid sampled speed differences, limited by your ${sensitivity}% scenario cap. This is a configurable heuristic, not a vehicle-specific model.`} />
            <Result label={`Total estimated ${isEv ? 'energy' : 'fuel'}`} value={result.total === null ? 'Unavailable' : `${result.total.toFixed(2)} ${unit}`} detail="Total is the baseline estimate plus the estimated additional use. If additional use is unavailable, the total is unavailable too." />
            <Result label="Estimated additional cost" value={result.additional_cost === null ? 'Unavailable' : `₹${result.additional_cost.toFixed(2)}`} detail="Estimated additional use multiplied by the fuel price or electricity tariff you entered. Cost is unavailable when no valid price was supplied." />
            {isEv && batteryCapacity !== '' && <Result label="Additional battery charge estimate" value={result.additional_battery_percent === null ? 'Unavailable' : `${result.additional_battery_percent.toFixed(2)}%`} detail="Estimated additional energy expressed as a share of the battery capacity you entered. This is approximate and does not model vehicle-specific battery behavior." />}
            {isEv && batteryCharge !== '' && batteryCapacity !== '' && <Result label="Estimated charge after trip" value={result.estimated_remaining_charge_percent === null ? 'Unavailable' : `${result.estimated_remaining_charge_percent.toFixed(1)}%${result.estimated_remaining_charge_percent < 0 ? ' · exceeds entered charge' : ''}`} detail="Estimate based on your entered starting charge, battery capacity, baseline energy, and additional energy scenario." />}
          </div>
          {result.traffic_latest_retrieved_at && <p className="fuel-small-note">Traffic samples retrieved: {new Date(result.traffic_latest_retrieved_at).toLocaleString()}{result.traffic_latest_observation_at ? ` · provider observation ${new Date(result.traffic_latest_observation_at).toLocaleString()}` : ' · provider observation time unavailable'}.</p>}
        </>}
      </section>
      </form>

      <section className="fuel-impact-panel fuel-context-grid" aria-label="Traffic and weather details">
        <details className="fuel-context-card">
          <summary><span>Traffic samples</span><strong>{result ? `${result.sample_count} valid` : traffic ? 'Available after estimate' : 'Unavailable'}</strong></summary>
          <div className="fuel-expanded-copy">
            <p>{result ? `Coverage: ${result.traffic_coverage}.` : 'Plan a route in SmartCommute AI to transfer its sampled traffic, then calculate to validate paired current/free-flow observations.'}</p>
            <p>Speed bands are heuristic comparisons of sampled point speeds. They do not identify an exact bottleneck count or measure idling time.</p>
          </div>
        </details>
        <details className="fuel-context-card">
          <summary><span>Weather forecast</span><strong>{weather ? `${weather.covered_location_count}/${weather.sampled_location_count} points` : 'Unavailable'}</strong></summary>
          <div className="fuel-expanded-copy">
            {weather ? <>
              <p>{weather.provider} forecast · {weather.status}{weather.stale ? ' · may be stale' : ''}</p>
              <p>Average temperature: {weather.avg_temperature_c ?? 'Unavailable'} °C · precipitation: {weather.avg_precipitation_mm_per_hour ?? 'Unavailable'} mm/h.</p>
              {weather.retrieved_at && <p>Retrieved {new Date(weather.retrieved_at).toLocaleString()}.</p>}
            </> : <p>No route weather forecast was transferred. No weather adjustment is applied.</p>}
          </div>
        </details>
      </section>

      {result && <details className="fuel-calculation-details">
        <summary>How is this calculated?</summary>
        <div className="fuel-expanded-copy">
          <p>Baseline {isEv ? 'energy' : 'fuel'} = route distance ÷ entered efficiency (EV: distance × kWh/100 km ÷ 100). Additional use uses the backend scenario formula: {result.formula} The scenario cap is {sensitivity}%.</p>
          <p>{result.limitations}</p>
          <p>Weather adjustment: not applied. {result.weather_adjustment_reason}</p>
          <p>No idle-time estimate is calculated. Actual consumption varies with driving style, load, vehicle condition, weather, and EV regeneration strategy.</p>
        </div>
      </details>}

      <section className="fuel-impact-panel" aria-labelledby="data-status-heading">
        <h2 id="data-status-heading">Data used</h2>
        <p>Submitted incident reports are tracked in <Link to="/reports">Reports</Link>. Only verified, unresolved reports appear as active alerts.</p>
        {route?.traffic?.status === 'unavailable' && <p role="status">TomTom traffic is unavailable for this transferred route. Additional impact is unavailable; baseline use can still be estimated.</p>}
        {weather?.status === 'unavailable' && <p role="status">Weather forecast data is unavailable. No weather adjustment has been applied.</p>}
      </section>
    </div>
  )
}

function Result({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <details className="fuel-result">
    <summary><span>{label}</span><strong>{value}</strong><small>View details</small></summary>
    <p>{detail}</p>
  </details>
}

export default FuelImpactEstimator

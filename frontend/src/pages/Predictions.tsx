import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getPEMS08Status,
  predictPEMS08Congestion,
  predictPEMS08Speed,
  predictionErrorMessage,
} from '../services/predictions'
import type {
  PEMS08CongestionPrediction,
  PEMS08Features,
  PEMS08SpeedPrediction,
  PEMS08Status,
} from '../types/predictions'

type MeasurementField = {
  name: keyof Pick<
    PEMS08Features,
    | 'flow'
    | 'occupancy'
    | 'speed'
    | 'flow_lag_5m'
    | 'flow_lag_15m'
    | 'flow_lag_30m'
    | 'flow_lag_1h'
    | 'speed_lag_5m'
    | 'speed_lag_15m'
    | 'speed_lag_30m'
    | 'speed_lag_1h'
    | 'occupancy_lag_5m'
    | 'occupancy_lag_15m'
    | 'occupancy_lag_30m'
    | 'occupancy_lag_1h'
  >
  label: string
}

const measurementFields: MeasurementField[] = [
  { name: 'flow', label: 'Flow (current)' },
  { name: 'flow_lag_5m', label: 'Flow (5 minutes ago)' },
  { name: 'flow_lag_15m', label: 'Flow (15 minutes ago)' },
  { name: 'flow_lag_30m', label: 'Flow (30 minutes ago)' },
  { name: 'flow_lag_1h', label: 'Flow (1 hour ago)' },
  { name: 'occupancy', label: 'Occupancy (current)' },
  { name: 'occupancy_lag_5m', label: 'Occupancy (5 minutes ago)' },
  { name: 'occupancy_lag_15m', label: 'Occupancy (15 minutes ago)' },
  { name: 'occupancy_lag_30m', label: 'Occupancy (30 minutes ago)' },
  { name: 'occupancy_lag_1h', label: 'Occupancy (1 hour ago)' },
  { name: 'speed', label: 'Speed (current)' },
  { name: 'speed_lag_5m', label: 'Speed (5 minutes ago)' },
  { name: 'speed_lag_15m', label: 'Speed (15 minutes ago)' },
  { name: 'speed_lag_30m', label: 'Speed (30 minutes ago)' },
  { name: 'speed_lag_1h', label: 'Speed (1 hour ago)' },
]

// A real PEMS08 training-dataset row at sensor 0, 2016-07-01 01:00,
// including that sensor's measured values at the required lag offsets.
const recordedExample: Record<MeasurementField['name'], string> = {
  flow: '87',
  flow_lag_5m: '93',
  flow_lag_15m: '93',
  flow_lag_30m: '130',
  flow_lag_1h: '133',
  occupancy: '0.0451',
  occupancy_lag_5m: '0.0496',
  occupancy_lag_15m: '0.0477',
  occupancy_lag_30m: '0.0566',
  occupancy_lag_1h: '0.0603',
  speed: '66.7',
  speed_lag_5m: '64.3',
  speed_lag_15m: '65.7',
  speed_lag_30m: '66.4',
  speed_lag_1h: '65.8',
}

function localDateTimeInputValue(date: Date): string {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return localDate.toISOString().slice(0, 16)
}

function Predictions() {
  const [status, setStatus] = useState<PEMS08Status | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [featureTime, setFeatureTime] = useState(() => localDateTimeInputValue(new Date()))
  const [sensorId, setSensorId] = useState('')
  const [values, setValues] = useState<Record<MeasurementField['name'], string>>(
    () => Object.fromEntries(measurementFields.map(({ name }) => [name, ''])) as Record<MeasurementField['name'], string>,
  )
  const [mode, setMode] = useState<'speed' | 'congestion'>('speed')
  const [predictionLoading, setPredictionLoading] = useState(false)
  const [predictionError, setPredictionError] = useState<string | null>(null)
  const [speedResult, setSpeedResult] = useState<PEMS08SpeedPrediction | null>(null)
  const [congestionResult, setCongestionResult] = useState<PEMS08CongestionPrediction | null>(null)

  useEffect(() => {
    let active = true
    setStatusLoading(true)
    getPEMS08Status()
      .then((result) => {
        if (active) {
          setStatus(result)
          setStatusError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) setStatusError(predictionErrorMessage(error))
      })
      .finally(() => {
        if (active) setStatusLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPredictionLoading(true)
    setPredictionError(null)
    setSpeedResult(null)
    setCongestionResult(null)

    const timestamp = new Date(featureTime)
    if (Number.isNaN(timestamp.getTime())) {
      setPredictionError('Enter a valid feature timestamp.')
      setPredictionLoading(false)
      return
    }
    if (!/^\d+$/.test(sensorId) || Number(sensorId) > 169) {
      setPredictionError('Enter a PEMS08 sensor ID from 0 through 169.')
      setPredictionLoading(false)
      return
    }

    const dayOfWeek = (timestamp.getDay() + 6) % 7
    const hour = timestamp.getHours()
    const isWeekend = dayOfWeek >= 5
    const features = {
      ...Object.fromEntries(
        measurementFields.map(({ name }) => [name, Number(values[name])]),
      ),
      hour,
      day_of_week: dayOfWeek,
      month: timestamp.getMonth() + 1,
      is_weekend: Number(isWeekend),
      is_rush_hour: Number(
        !isWeekend && (hour >= 7 && hour <= 9 || hour >= 17 && hour <= 19),
      ),
    } as PEMS08Features

    try {
      if (mode === 'speed') {
        setSpeedResult(await predictPEMS08Speed(features))
      } else {
        setCongestionResult(await predictPEMS08Congestion(features))
      }
    } catch (error) {
      setPredictionError(predictionErrorMessage(error))
    } finally {
      setPredictionLoading(false)
    }
  }

  function loadRecordedExample() {
    setSensorId('0')
    setFeatureTime('2016-07-01T01:00')
    setValues(recordedExample)
    setPredictionError(null)
    setSpeedResult(null)
    setCongestionResult(null)
  }

  const predictionTime = Number.isNaN(new Date(featureTime).getTime())
    ? null
    : new Date(new Date(featureTime).getTime() + 60 * 60 * 1000).toLocaleString()
  const modelUnavailable = mode === 'speed'
    ? !status?.speed_model_available
    : !status?.congestion_model_available

  return (
    <section>
      <h1>Advanced PEMS08 predictions</h1>
      <p>
        Looking for a commuter trip assessment? <Link to="/simulations">Plan a trip here</Link> to compare routes,
        weather, and available incident reports.
      </p>
      <p>
        Runs the existing PEMS08 model on manually supplied measurements for one PEMS08 sensor.
        Predictions are for T+1 hour and are not linked to application roads.
      </p>
      <p>
        The sensor ID is only a user-side reference: it is not one of the model's 20 input
        features. The application cannot verify the origin of manually entered values.
      </p>

      {statusLoading && <p role="status">Checking PEMS08 model artifacts...</p>}
      {statusError && <p role="alert">Model availability could not be checked: {statusError}</p>}
      {status && (
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <strong>Input source: PEMS08 only</strong>
          <p>
            {status.speed_model_available ? 'Speed model available' : 'Speed model artifact unavailable'}
            {' · '}
            {status.congestion_model_available
              ? 'Congestion model available'
              : 'Congestion model artifact unavailable'}
            {' · '}{status.feature_count} ordered features · horizon {status.prediction_horizon}
          </p>
          <ul>
            {status.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </div>
      )}

      <form onSubmit={(event) => void handleSubmit(event)}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
          <label>
            PEMS08 sensor ID (0–169)
            <input
              type="number"
              min={0}
              max={169}
              step={1}
              required
              value={sensorId}
              onChange={(event) => setSensorId(event.target.value)}
              style={{ display: 'block', padding: 8, marginTop: 4 }}
            />
          </label>
          <label>
            Feature timestamp (local)
            <input
              type="datetime-local"
              required
              value={featureTime}
              onChange={(event) => setFeatureTime(event.target.value)}
              style={{ display: 'block', padding: 8, marginTop: 4 }}
            />
          </label>
        </div>

        <p>
          Enter current and lag measurements from the same sensor at the selected time.
          Flow and occupancy use the raw PEMS08 dataset values. Speed units are not
          independently verified; do not interpret the output as km/h.
        </p>
        <button type="button" onClick={loadRecordedExample}>
          Load recorded PEMS08 example
        </button>
        <p role="note">
          The example is a historical PEMS08 training-data observation (sensor 0, July 1, 2016),
          not live traffic and not an application-road measurement.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          {measurementFields.map(({ name, label }) => (
            <label key={name}>
              {label}
              <input
                type="number"
                min={0}
                step="any"
                required
                value={values[name]}
                onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
                style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: 8, marginTop: 4 }}
              />
            </label>
          ))}
        </div>

        <fieldset style={{ margin: '16px 0' }}>
          <legend>Prediction task</legend>
          <label style={{ marginRight: 16 }}>
            <input
              type="radio"
              name="prediction-mode"
              checked={mode === 'speed'}
              onChange={() => setMode('speed')}
            />
            Speed forecast
          </label>
          <label>
            <input
              type="radio"
              name="prediction-mode"
              checked={mode === 'congestion'}
              onChange={() => setMode('congestion')}
            />
            Congestion classification
          </label>
        </fieldset>

        {predictionError && <p role="alert">{predictionError}</p>}
        <button
          type="submit"
          disabled={statusLoading || statusError !== null || modelUnavailable || predictionLoading}
        >
          {predictionLoading ? 'Running model...' : 'Run PEMS08 prediction'}
        </button>
        {status && modelUnavailable && (
          <p role="alert">The selected model artifact is unavailable; no prediction was run.</p>
        )}
      </form>

      {speedResult && (
        <section aria-live="polite">
          <h2>Speed forecast result</h2>
          <p>
            {speedResult.predicted_speed.toFixed(2)} ({speedResult.speed_unit_note})
          </p>
          <p>
            Model: {speedResult.model} · Horizon: {speedResult.prediction_horizon}
            {predictionTime ? ` · Target time: ${predictionTime}` : ''}
          </p>
        </section>
      )}
      {congestionResult && (
        <section aria-live="polite">
          <h2>Congestion forecast result</h2>
          <p>
            {congestionResult.congestion_level} at {predictionTime ?? 'T+1 hour'}
          </p>
          <p>
            Model: {congestionResult.model} · Horizon: {congestionResult.prediction_horizon}
          </p>
          <ul>
            {Object.entries(congestionResult.probabilities).map(([label, probability]) => (
              <li key={label}>{label}: {(probability * 100).toFixed(1)}%</li>
            ))}
          </ul>
          <p role="note">{congestionResult.probability_note}</p>
          <p>Congestion classes are relative to the PEMS08 training data, not application road conditions.</p>
        </section>
      )}
    </section>
  )
}

export default Predictions

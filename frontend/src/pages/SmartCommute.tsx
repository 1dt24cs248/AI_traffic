import { ScenarioPlanner } from './Simulations'

function SmartCommute() {
  return (
    <div className="smartcommute-page">
      <header className="scenario-hero smartcommute-hero">
        <p className="eyebrow">SMARTCOMMUTE AI · JOURNEY PLANNING</p>
        <h1>SmartCommute AI</h1>
        <p className="smartcommute-subtitle">A clearer trip comparison, grounded in available evidence.</p>
        <p>
          Compare route options using road distance, baseline routing time, sampled current traffic,
          provider weather forecasts, and nearby incident reports.
        </p>
        <p className="smartcommute-limit" role="note">
          Bengaluru future congestion forecasts are not validated. PEMS08 is a separate dataset and
          is not mapped to these roads. Route recommendations use available routing and hazard
          evidence, not an AI traffic prediction or safety probability.
        </p>
      </header>
      <ScenarioPlanner showSimulationTools={false} />
    </div>
  )
}

export default SmartCommute

import { Link } from 'react-router-dom'
import { isAuthenticated } from '../services/auth'
import { getFeatureCardNavigation } from '../services/authNavigation.mjs'

const features = [
  ['01', 'SmartCommute AI', 'Compare route alternatives with available traffic, weather, and incident evidence.', '/predictions'],
  ['02', 'Live map & routing', 'Explore routes and sampled provider traffic on an interactive map.', '/map'],
  ['03', 'Traffic dashboard', 'Review stored observations, trends, peak periods, and source coverage.', '/dashboard'],
  ['04', 'Fuel & energy impact', 'Explore a transparent, adjustable scenario estimate for a planned route.', '/simulations'],
  ['05', 'Incident reporting', 'Report a road hazard from the map and follow its review status in Reports.', '/map'],
  ['06', 'Verified alerts', 'See active alerts after reports are verified and remain unresolved.', '/alerts'],
  ['07', 'Traffic analytics', 'Filter historical records by available source and observation period.', '/dashboard'],
  ['08', 'Simulations', 'Review saved synthetic scenario summaries, kept separate from observed traffic.', '/reports'],
]

function LandingPage() {
  const startPath = isAuthenticated() ? '/dashboard' : '/register'

  return (
    <div className="landing-page">
      <header className="landing-nav-wrap">
        <nav className="landing-nav" aria-label="Public navigation">
          <a className="landing-brand" href="#top" aria-label="AI Traffic Flow Predictor home">
            <span className="brand-mark" aria-hidden="true"><BrandMark /></span>
            <span>SmartCommute <small>TRAFFIC INTELLIGENCE</small></span>
          </a>
          <div className="landing-nav-links">
            <a href="#top">Home</a>
            <a href="#about">About</a>
            <a href="#how-it-works">How it works</a>
            <a href="#features">Features</a>
            <a href="#technology">Technology</a>
          </div>
          <div className="landing-auth-links">
            <Link className="landing-signin" to="/login">Sign in</Link>
            <Link className="button button-primary landing-register" to="/register">Register</Link>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <p className="landing-kicker"><span className="live-dot" /> URBAN MOBILITY, MADE CLEARER</p>
            <h1>AI Traffic Flow Predictor</h1>
            <p className="landing-hero-subtitle">Intelligent traffic insights and smarter route planning.</p>
            <p className="landing-hero-description">
              Bring route options, available traffic observations, weather context, incident reports,
              and historical analytics into one clear view.
            </p>
            <div className="landing-hero-actions">
              <Link className="button button-primary" to={startPath}>{isAuthenticated() ? 'Explore dashboard' : 'Get started'} <span aria-hidden="true">→</span></Link>
              <a className="button button-quiet" href="#how-it-works">How it works</a>
            </div>
            <p className="landing-disclaimer">Route times are provider estimates. Bengaluru future traffic predictions are not validated.</p>
          </div>
          <div className="traffic-visual" aria-label="Illustrative map-inspired traffic panel; no live traffic data shown">
            <div className="visual-topline"><span>TRAFFIC CONTEXT</span><span className="visual-status"><i /> illustrative view</span></div>
            <div className="mini-map" aria-hidden="true">
              <svg viewBox="0 0 600 320" role="presentation">
                <path className="map-road map-road-major" d="M-10 260 C100 225 145 270 225 214 S360 146 610 190" />
                <path className="map-road" d="M-8 75 C105 110 130 75 225 117 S395 238 605 258" />
                <path className="map-road" d="M83 -10 C110 80 201 130 192 330" />
                <path className="map-road" d="M470 -10 C410 92 430 184 520 330" />
                <path className="map-road" d="M-5 160 C125 175 330 28 620 54" />
                <path className="map-route" d="M-10 260 C100 225 145 270 225 214 S360 146 610 190" />
                <circle className="map-point map-point-start" cx="107" cy="243" r="7" />
                <circle className="map-point map-point-end" cx="489" cy="170" r="7" />
              </svg>
              <span className="map-label map-label-one">Route options</span>
              <span className="map-label map-label-two">Observed · forecast · reported</span>
            </div>
            <div className="visual-legend"><span><i className="legend-violet" />Route</span><span><i className="legend-teal" />Information sources</span><span><i className="legend-muted" />Illustration only</span></div>
          </div>
        </section>

        <section id="about" className="landing-section landing-about" aria-label="Project overview">
          <div className="section-heading"><p className="landing-kicker">WHY SMARTCOMMUTE</p><h2>Traffic context, with the evidence in view.</h2></div>
          <p className="landing-section-copy">
            Urban congestion changes by road, time, and conditions. SmartCommute brings together the
            information currently available to the project so people can compare journeys and understand
            what each result represents. Live provider observations, stored historical records, weather
            forecasts, submitted reports, and simulations remain clearly distinguished.
          </p>
        </section>

        <section id="how-it-works" className="landing-section">
          <div className="section-heading"><p className="landing-kicker">A CLEARER WORKFLOW</p><h2>From journey question to useful context.</h2></div>
          <ol className="workflow-grid">
            <WorkflowStep number="01" title="Choose a journey" text="Enter an origin and destination in SmartCommute AI, or explore stored traffic analytics." />
            <WorkflowStep number="02" title="Gather available context" text="The app retrieves supported route alternatives and available traffic, weather, and incident information." />
            <WorkflowStep number="03" title="Compare the evidence" text="Review route distance, baseline time estimates, sample coverage, and relevant reports." />
            <WorkflowStep number="04" title="Explore impact & trends" text="Estimate fuel or energy scenarios and examine historical or simulated traffic separately." />
          </ol>
        </section>

        <section id="features" className="landing-section">
          <div className="section-heading"><p className="landing-kicker">PLATFORM CAPABILITIES</p><h2>Tools for the full traffic picture.</h2></div>
          <div className="feature-grid">
            {features.map(([number, title, description, href]) => (
              <Link className="landing-feature" {...getFeatureCardNavigation(href, isAuthenticated())} key={title}>
                <span className="feature-number">{number}</span><h3>{title}</h3><p>{description}</p><span className="feature-arrow" aria-hidden="true">↗</span>
              </Link>
            ))}
          </div>
        </section>

        <section id="technology" className="landing-section technology-section">
          <div className="section-heading"><p className="landing-kicker">BUILT WITH</p><h2>A practical, connected foundation.</h2></div>
          <div className="technology-list" aria-label="Project technologies">
            {['React · TypeScript · Vite', 'Python · FastAPI', 'PostgreSQL · SQLAlchemy · Alembic', 'OSRM · TomTom Traffic', 'Open-Meteo', 'scikit-learn · existing traffic ML pipeline'].map((technology) => <span key={technology}>{technology}</span>)}
          </div>
          <p className="technology-note">Traffic forecast limitations remain explicit: the current models do not validate future congestion for Bengaluru application roads.</p>
        </section>
      </main>

      <footer className="landing-footer">
        <a className="landing-brand" href="#top"><span className="brand-mark" aria-hidden="true"><BrandMark /></span><span>AI Traffic Flow Predictor</span></a>
        <p>Traffic insights with clear sources, context, and limitations.</p>
        <div className="footer-links"><a href="#about">About</a><a href="#features">Features</a><Link to="/login">Sign in</Link><Link to="/register">Register</Link></div>
      </footer>
    </div>
  )
}

function WorkflowStep({ number, title, text }: { number: string; title: string; text: string }) {
  return <li className="workflow-step"><span>{number}</span><h3>{title}</h3><p>{text}</p></li>
}

function BrandMark() {
  return <svg viewBox="0 0 24 24" fill="none"><path d="M4 18.5 9 5.5l4.8 13 2.1-6h4.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="4" cy="18.5" r="1.6" fill="currentColor"/><circle cx="20" cy="12.5" r="1.6" fill="currentColor"/></svg>
}

export default LandingPage

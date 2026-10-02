import { Link, Outlet, useNavigate } from 'react-router-dom'
import { logout } from '../services/auth'

const UPCOMING_SECTIONS = ['Predictions', 'Alerts', 'Reports']
function AppLayout() {
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav
        style={{
          width: 220,
          borderRight: '1px solid #ddd',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <div style={{ fontWeight: 'bold', marginBottom: '16px' }}>AI Traffic Flow Predictor</div>

        <Link to="/home">Home</Link>
        <Link to="/dashboard">Dashboard</Link>

        <div style={{ marginTop: '16px', fontSize: '12px', color: '#888', textTransform: 'uppercase' }}>
          Coming soon
        </div>
       <Link to="/map">Map & Routing</Link>

{UPCOMING_SECTIONS.map((section) => (
  <span key={section} style={{ color: '#aaa' }}>
    {section}
  </span>
))}
        <button onClick={handleLogout} style={{ marginTop: 'auto' }}>
          Logout
        </button>
      </nav>

      <main style={{ flex: 1, padding: '24px' }}>
        <Outlet />
      </main>
    </div>
  )
}

export default AppLayout
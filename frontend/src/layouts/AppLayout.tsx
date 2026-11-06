import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../services/auth'

function AppLayout() {
  const navigate = useNavigate()
  const [adminAccess, setAdminAccess] = useState<'checking' | 'allowed' | 'denied' | 'unknown'>('checking')

  useEffect(() => {
    let active = true
    getCurrentUser()
      .then((user) => {
        if (active) setAdminAccess(user.role === 'ADMIN' ? 'allowed' : 'denied')
      })
      .catch(() => {
        if (active) setAdminAccess('unknown')
      })
    return () => {
      active = false
    }
  }, [])

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-brand" to="/" aria-label="AI Traffic Flow Predictor public home">AI Traffic Flow Predictor</Link>
        <nav className="app-nav" aria-label="Main navigation">
          <NavLink to="/home" className="nav-group-label">Overview</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <div className="nav-group-label">Journey</div>
          <NavLink to="/predictions">SmartCommute AI</NavLink>
          <NavLink to="/map">Map &amp; Routing</NavLink>
          <div className="nav-group-label">Insights</div>
          <NavLink to="/simulations">Fuel &amp; Energy Estimator</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <NavLink to="/alerts">Alerts</NavLink>
          {adminAccess === 'allowed' && <NavLink to="/admin/incidents">Incident moderation</NavLink>}
        </nav>
        <button className="app-logout" onClick={handleLogout}>
          Logout
        </button>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}

export default AppLayout

import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getCurrentUser, isAuthenticated } from '../services/auth'
import { getProtectedRouteLoginState } from '../services/authNavigation.mjs'

function ProtectedRoute() {
  const location = useLocation()
  const [sessionState, setSessionState] = useState<'checking' | 'authenticated' | 'unauthenticated'>(
    () => isAuthenticated() ? 'checking' : 'unauthenticated',
  )

  useEffect(() => {
    let active = true
    if (!isAuthenticated()) {
      setSessionState('unauthenticated')
      return () => { active = false }
    }

    getCurrentUser()
      .then(() => { if (active) setSessionState('authenticated') })
      .catch(() => { if (active) setSessionState('unauthenticated') })

    return () => { active = false }
  }, [])

  if (sessionState === 'checking') {
    return <div role="status" className="route-auth-status">Verifying your session…</div>
  }
  if (sessionState === 'unauthenticated') {
    return <Navigate to="/login" state={getProtectedRouteLoginState(location)} replace />
  }
  return <Outlet />
}

export default ProtectedRoute

import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import LandingPage from './pages/LandingPage'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import MapRouting from './pages/MapRouting'
import AdminIncidents from './pages/AdminIncidents'
import Simulations from './pages/Simulations'
import SmartCommute from './pages/SmartCommute'
import Alerts from './pages/Alerts'
import Reports from './pages/Reports'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/home" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/map" element={<MapRouting />} />
          <Route path="/admin/incidents" element={<AdminIncidents />} />
          <Route path="/simulations" element={<Simulations />} />
          <Route path="/predictions" element={<SmartCommute />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/reports" element={<Reports />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App

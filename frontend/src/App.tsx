import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import MapRouting from './pages/MapRouting'
import { isAuthenticated } from './services/auth'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/home" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/map" element={<MapRouting />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to={isAuthenticated() ? '/home' : '/login'} replace />} />
    </Routes>
  )
}

export default App
import { FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { login } from '../services/auth'
import { getPostLoginPath, getRegistrationLoginState } from '../services/authNavigation.mjs'

function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      navigate(getPostLoginPath(location.state), { replace: true })
    } catch (err) {
      setError('Login failed. Check your email and password and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-card">
        <p className="auth-brand">AI Traffic Flow Predictor</p>
        <h1>Welcome back</h1>
        <p className="auth-description">Sign in to plan trips and review local traffic information.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="email">Email</label>
          <br />
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <br />
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p role="alert" className="auth-error">{error}</p>}
        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>
      <p className="auth-footer">
        Don&apos;t have an account? <Link to="/register" state={getRegistrationLoginState(location.state)}>Register</Link>
      </p>
      </section>
    </div>
  )
}

export default Login

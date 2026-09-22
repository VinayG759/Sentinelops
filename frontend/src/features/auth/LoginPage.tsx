import { Shield } from 'lucide-react'
import { motion } from 'motion/react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { supabase } from '@/shared/supabase'

type Mode = 'signin' | 'signup'

export function LoginPage() {
  const { session } = useAuth()
  const location = useLocation()
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (session) {
    const from = (location.state as { from?: string } | null)?.from ?? '/overview'
    return <Navigate to={from} replace />
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    const { data, error } =
      mode === 'signin'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
    setBusy(false)
    if (error) return setError(error.message)
    if (mode === 'signup' && !data.session) {
      setNotice('Check your email to confirm the account, then sign in.')
      setMode('signin')
    }
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden p-6">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            'radial-gradient(60% 50% at 50% 0%, oklch(0.72 0.145 220 / 12%), transparent 70%)',
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative w-full max-w-sm"
      >
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-signal/12 ring-1 ring-signal/25">
            <Shield className="size-4 text-signal" />
          </div>
          <div>
            <div className="font-semibold tracking-tight">SentinelOps</div>
            <div className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
              autonomous sre · safety gated
            </div>
          </div>
        </div>

        <h1 className="mt-7 text-xl font-semibold tracking-tight">
          {mode === 'signin' ? 'Sign in' : 'Create an account'}
        </h1>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          Detect, diagnose and fix production incidents — with a human in the loop.
        </p>

        <form onSubmit={submit} className="panel mt-5 space-y-4 p-5">
          <div className="space-y-1.5">
            <Label htmlFor="email" className="text-[11.5px]">
              Email
            </Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-surface-sunken"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password" className="text-[11.5px]">
              Password
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-surface-sunken"
            />
          </div>
          {error && <p className="text-[12px] text-sev1">{error}</p>}
          {notice && <p className="text-[12px] text-muted-foreground">{notice}</p>}
          <Button
            type="submit"
            disabled={busy}
            className="w-full bg-signal text-primary-foreground hover:bg-signal/90"
          >
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </Button>
        </form>

        <p className="mt-4 text-center text-[12px] text-muted-foreground">
          {mode === 'signin' ? 'No account yet?' : 'Already have an account?'}{' '}
          <button
            type="button"
            className="text-signal underline-offset-4 hover:underline"
            onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
          >
            {mode === 'signin' ? 'Create one' : 'Sign in'}
          </button>
        </p>
      </motion.div>
    </div>
  )
}

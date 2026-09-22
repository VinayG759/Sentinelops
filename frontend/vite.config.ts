import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// One .env at the repo root is shared with the backend. It holds real secrets,
// so we expose ONLY the two public Supabase values to the browser bundle —
// never an `envPrefix` that could leak SUPABASE_SECRET_KEY or SUPABASE_DB_URL.
const repoRoot = path.resolve(__dirname, '..')

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, '')
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
    define: {
      'import.meta.env.SUPABASE_URL': JSON.stringify(env.SUPABASE_URL),
      'import.meta.env.SUPABASE_PUBLISHABLE_KEY': JSON.stringify(env.SUPABASE_PUBLISHABLE_KEY),
    },
    server: {
      // Same-origin /api means one public URL (tunnel) serves both frontend and backend.
      proxy: { '/api': 'http://localhost:8000' },
    },
  }
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// TLS is opt-in via SSL_CERTFILE/SSL_KEYFILE so this same config serves plain
// HTTP for local dev (`npm run dev`, docker-compose) and HTTPS when deployed
// via Helm (infra/helm/charts/frontend), which mounts a cert-manager-issued
// Secret and sets these vars — see frontend/docker-entrypoint.sh. The chart's
// readiness/liveness probes and Service both expect HTTPS on the same port
// 3000 the container already serves plain HTTP on today, so no port change.
const sslCertFile = process.env.SSL_CERTFILE
const sslKeyFile = process.env.SSL_KEYFILE
const https =
  sslCertFile && sslKeyFile
    ? { cert: fs.readFileSync(sslCertFile), key: fs.readFileSync(sslKeyFile) }
    : undefined

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    https,
    proxy: {
      '/api': {
        target: process.env.BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})

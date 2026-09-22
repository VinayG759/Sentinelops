const express = require('express');
const { Pool } = require('pg');
const client = require('prom-client');

const app = express();
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const requestCounter = new client.Counter({
  name: 'order_requests_total',
  help: 'Total requests handled by order-service',
  registers: [register]
});
const errorCounter = new client.Counter({
  name: 'order_errors_total',
  help: 'Total errors in order-service',
  registers: [register]
});
const latencyHistogram = new client.Histogram({
  name: 'order_request_duration_ms',
  help: 'Request latency in milliseconds',
  buckets: [10, 50, 100, 500, 1000, 3000, 5000, 10000],
  registers: [register]
});

const POOL_MAX = 8;

const pool = new Pool({
  host: process.env.PG_HOST || 'postgres',
  port: parseInt(process.env.PG_PORT || '5432', 10),
  user: process.env.PG_USER || 'sentinel',
  password: process.env.PG_PASSWORD || 'sentinel',
  database: process.env.PG_DATABASE || 'sentinelops',
  max: POOL_MAX,
  connectionTimeoutMillis: 3000
});

pool.on('error', (err) => {
  console.error('Idle client error', err.message);
});

// Connection-pool gauges, read at scrape time. Prometheus adds the `app` label,
// so the names are shared across services. These are what let an investigator
// prove pool exhaustion (waiting > 0) rather than guess it.
const poolGauges = [
  ['db_pool_total', 'Connections currently open in the pool', () => pool.totalCount],
  ['db_pool_idle', 'Open connections not in use', () => pool.idleCount],
  ['db_pool_waiting', 'Queries queued waiting for a connection', () => pool.waitingCount],
  ['db_pool_max', 'Configured maximum pool size', () => POOL_MAX],
];
for (const [name, help, read] of poolGauges) {
  new client.Gauge({ name, help, registers: [register], collect() { this.set(read()); } });
}

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'order-service' });
});

app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

async function simulateTraffic() {
  const start = Date.now();
  requestCounter.inc();
  try {
    await pool.query('SELECT 1');
    latencyHistogram.observe(Date.now() - start);
  } catch (err) {
    errorCounter.inc();
    latencyHistogram.observe(Date.now() - start);
    console.error('order-service query error:', err.message);
  }
}

setInterval(simulateTraffic, 500);

const PORT = process.env.PORT || 4002;
app.listen(PORT, () => console.log(`order-service listening on ${PORT}`));

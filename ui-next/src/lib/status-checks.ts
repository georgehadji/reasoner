/**
 * The checks `GET /api/health` reports, in the order it reports them, and
 * what each one actually tests. Mirrored by hand from
 * `src/reasoner/application/services/health_service.py` (`check_health`);
 * update both together.
 */
export type CheckStatus = 'ok' | 'warning' | 'degraded' | 'error' | 'unknown';

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export interface HealthResponse {
  status: HealthStatus;
  timestamp?: string;
  checks?: Record<string, { status: CheckStatus; reason?: string }>;
  error?: string;
}

export const HEALTH_CHECKS: Array<{ key: string; name: string; tests: string; fails: string }> = [
  {
    key: 'memory',
    name: 'Application memory',
    tests: 'Memory held by the API process',
    fails: 'Warning above its configured limit',
  },
  {
    key: 'circuit_breakers',
    name: 'Model providers',
    tests: 'Whether any provider’s circuit breaker is open',
    fails: 'Degraded while one is open',
  },
  {
    key: 'cache',
    name: 'Response cache',
    tests: 'Nothing yet: it always reports OK',
    fails: 'Never',
  },
  {
    key: 'postgres',
    name: 'Database',
    tests: 'A SELECT 1 through a probe connection',
    fails: 'Error if the query fails',
  },
  {
    key: 'valkey',
    name: 'Cache and rate-limit store',
    tests: 'A PING to Valkey, answered within 5 seconds',
    fails: 'Error if it does not answer',
  },
  {
    key: 'stripe',
    name: 'Billing',
    tests: 'That a Stripe key is configured; Stripe itself is not called',
    fails: 'Never, in practice',
  },
];

/** The reason the backend gives when a dependency is simply not set up. */
export const NOT_CONFIGURED = 'not configured';

export const OVERALL: Record<HealthStatus | 'unreachable', string> = {
  healthy: 'All systems operational',
  degraded: 'Degraded performance',
  unhealthy: 'Service disruption',
  unreachable: 'The API did not answer',
};

export const CHECK_WORD: Record<CheckStatus, string> = {
  ok: 'OK',
  warning: 'Warning',
  degraded: 'Degraded',
  error: 'Error',
  unknown: 'Unknown',
};

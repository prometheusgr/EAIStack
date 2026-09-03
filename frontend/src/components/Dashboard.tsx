import { useEffect } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useSettingsService } from '@/hooks/useSettingsService'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface DashboardProps {
  /** Switches the main nav to the full Audit Log view (issue #45) -- the
   * recent-activity tile below is a small preview, not a replacement.
   */
  onViewAuditLog: () => void
}

/** Admin-only "system status at a glance" screen (issue #48). Assumes it is
 * only ever mounted for an admin user -- the mount point (App.tsx) is
 * responsible for that gate; this component does not check isAdmin itself.
 * Every tile is backed by a real data path (GET /api/settings/dashboard and
 * the existing audit log endpoint) -- see
 * app.services.dashboard_service.resolve_dashboard_status's docstring for
 * why a "recent 429 count" tile does not exist (no real data source).
 */
export function Dashboard({ onViewAuditLog }: DashboardProps) {
  const { isLoading: isAuthLoading } = useAuth()
  const { getDashboard, getAuditLog } = useSettingsService()

  useEffect(() => {
    // Wait for AuthContext's async init to finish resolving the token
    // before the first fetch -- firing earlier would hit the "no auth
    // token available" guard in useSettingsService.
    if (isAuthLoading) return
    getDashboard.execute()
    getAuditLog.execute()
  }, [isAuthLoading])

  if (getDashboard.isLoading && !getDashboard.data) {
    return (
      <div className="space-y-4">
        <div className="text-gray-500">Loading dashboard...</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    )
  }

  if (getDashboard.error && !getDashboard.data) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        <p>
          {getDashboard.error instanceof Error
            ? getDashboard.error.message
            : 'Failed to load dashboard'}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => getDashboard.execute()}
          className="mt-2"
        >
          Retry
        </Button>
      </div>
    )
  }

  const status = getDashboard.data
  if (!status) return null

  const guardrailPatternEntries = Object.entries(status.guardrails.input_rejected_counts_by_pattern)
  const tracingDiverges =
    status.tracing.db_desired_enabled !== status.tracing.process_actually_configured

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Dashboard</h2>
        <p className="text-sm text-gray-500">System status at a glance.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Rate Limiting</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-sm text-gray-500">
              {status.rate_limit.enabled ? 'Enabled' : 'Disabled'}
            </p>
            <p className="text-3xl font-semibold">{status.rate_limit.active_bucket_count}</p>
            <p className="text-sm text-gray-500">active buckets tracked</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Guardrails</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-gray-500">Trips in the last 24 hours</p>
            {guardrailPatternEntries.length === 0 ? (
              <p className="text-sm text-gray-500">No rejections</p>
            ) : (
              <ul className="text-sm space-y-1">
                {guardrailPatternEntries.map(([pattern, count]) => (
                  <li key={pattern} className="flex justify-between">
                    <span>{pattern}</span>
                    <span className="font-medium">{count}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-sm text-gray-500">
              Output redactions: <span className="font-medium">{status.guardrails.output_redacted_count}</span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tracing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-gray-500">
              Configured: {status.tracing.db_desired_enabled ? 'Enabled' : 'Disabled'}
            </p>
            <p className="text-sm text-gray-500">
              Active in this process: {status.tracing.process_actually_configured ? 'Yes' : 'No'}
            </p>
            {tracingDiverges && (
              <p className="text-sm text-amber-600">
                A backend restart is required for the configured setting to take effect.
              </p>
            )}
            <a
              href={status.tracing.phoenix_ui_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-primary underline"
            >
              Open Phoenix UI
            </a>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {getAuditLog.isLoading && !getAuditLog.data && (
              <p className="text-sm text-gray-500">Loading...</p>
            )}
            {getAuditLog.data && getAuditLog.data.entries.length === 0 && (
              <p className="text-sm text-gray-500">No recent activity</p>
            )}
            {getAuditLog.data && getAuditLog.data.entries.length > 0 && (
              <ul className="text-sm space-y-1">
                {getAuditLog.data.entries.slice(0, 5).map((entry) => (
                  <li key={entry.id} className="flex justify-between gap-2">
                    <span>{entry.action}</span>
                    <span className="text-gray-500">
                      {new Date(entry.created_at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Button variant="link" size="sm" className="px-0" onClick={onViewAuditLog}>
              View full audit log
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

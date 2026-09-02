import { useEffect } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useSettingsService } from '@/hooks/useSettingsService'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

/** Admin-only screen for viewing the audit trail of settings changes and
 * guardrail trips (issue #45). Assumes it is only ever mounted for an admin
 * user — the mount point (App.tsx) is responsible for that gate; this
 * component does not check isAdmin itself. Read-only: the backend exposes
 * no way to modify or delete an audit entry.
 */
export function AuditLog() {
  const { isLoading: isAuthLoading } = useAuth()
  const { getAuditLog } = useSettingsService()

  useEffect(() => {
    // Wait for AuthContext's async init to finish resolving the token
    // before the first fetch — firing earlier would hit the "no auth
    // token available" guard in useSettingsService.
    if (isAuthLoading) return
    getAuditLog.execute()
  }, [isAuthLoading])

  if (getAuditLog.isLoading && !getAuditLog.data) {
    return (
      <div className="space-y-4">
        <div className="text-gray-500">Loading audit log...</div>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    )
  }

  if (getAuditLog.error && !getAuditLog.data) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        <p>
          {getAuditLog.error instanceof Error
            ? getAuditLog.error.message
            : 'Failed to load audit log'}
        </p>
        <Button variant="outline" size="sm" onClick={() => getAuditLog.execute()} className="mt-2">
          Retry
        </Button>
      </div>
    )
  }

  const entries = getAuditLog.data?.entries ?? []

  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg">No audit entries yet</p>
        <p className="text-sm">Settings changes and guardrail trips will appear here.</p>
      </div>
    )
  }

  return (
    <section className="space-y-4" aria-label="Audit log">
      <div>
        <h2 className="text-lg font-semibold">Audit Log</h2>
        <p className="text-sm text-gray-500">
          A read-only history of settings changes and guardrail trips, newest first.
        </p>
      </div>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Field</TableHead>
              <TableHead>Old value</TableHead>
              <TableHead>New value</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell>{new Date(entry.created_at).toLocaleString()}</TableCell>
                <TableCell>{entry.actor_user_id}</TableCell>
                <TableCell className="font-medium">{entry.action}</TableCell>
                <TableCell>{entry.field_name}</TableCell>
                <TableCell>{entry.old_value ?? '—'}</TableCell>
                <TableCell>{entry.new_value ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

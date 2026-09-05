import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useSettingsService } from '@/hooks/useSettingsService'

/** Plain-language rendering of GET /api/settings/retention-notice's
 * conversation_retention_hours (issue #49). Retention windows were already
 * fully admin-configurable, but only visible via the admin-only Settings
 * screen -- this is the first place an ordinary chat user can see how long
 * their own conversation history is kept.
 */
function describeRetentionWindow(hours: number | null): string {
  if (hours === null) {
    return 'Your conversation history is kept indefinitely.'
  }
  if (hours === 0) {
    return 'Your conversation history is purged immediately after each session.'
  }
  if (hours === 1) {
    return 'Your conversation history is retained for 1 hour.'
  }
  if (hours % 24 === 0) {
    const days = hours / 24
    return `Your conversation history is retained for ${days} day${days === 1 ? '' : 's'}.`
  }
  return `Your conversation history is retained for ${hours} hours.`
}

export function RetentionNotice() {
  const { isLoading: isAuthLoading } = useAuth()
  const { getRetentionNotice } = useSettingsService()
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    // Same isAuthLoading gate Settings.tsx uses: AuthContext resolves the
    // token asynchronously, and firing before that resolves would hit the
    // "no auth token available" guard in useSettingsService.
    if (isAuthLoading) return
    getRetentionNotice.execute()
  }, [isAuthLoading])

  if (!getRetentionNotice.data || !getRetentionNotice.data.notice_enabled || dismissed) {
    return null
  }

  const { conversation_retention_hours, cleanup_on_logout } = getRetentionNotice.data

  return (
    <div
      role="status"
      aria-label="Data retention notice"
      className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted px-4 py-2 text-sm text-muted-foreground"
    >
      <p>
        {describeRetentionWindow(conversation_retention_hours)}
        {cleanup_on_logout &&
          ' It is also deleted as soon as you log out.'}
      </p>
      <button
        type="button"
        aria-label="Dismiss retention notice"
        onClick={() => setDismissed(true)}
        className="shrink-0 text-muted-foreground hover:text-foreground"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

import { Info } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface InfoTooltipProps {
  children: React.ReactNode
}

/** An (i) icon that reveals help text for a settings field on hover or
 * keyboard focus. Every instance shares the same generic accessible name
 * ("Show help") rather than naming the field it belongs to -- the trigger
 * always sits right after its field's own <label> text, so a field-specific
 * name (e.g. "Max input length help") would duplicate a substring of that
 * label and make screen.getByLabelText(/max input length/i) ambiguous
 * between the <label> and this button. A caller that needs to target one
 * specific tooltip (e.g. a test) should scope the query to the field's
 * containing element first.
 *
 * Relies on a single app-level TooltipProvider (mounted once in App.tsx,
 * alongside AuthProvider/ToastProvider) rather than wrapping its own here --
 * Radix's cross-tooltip "skip delay" grouping (hovering a second tooltip
 * shortly after closing the first opens it instantly) only works when
 * sibling tooltips share one Provider; a per-instance Provider would defeat
 * that on a page with 15+ tooltips. A caller rendering InfoTooltip outside
 * App's provider tree (e.g. a unit test) must supply its own TooltipProvider.
 */
export function InfoTooltip({ children }: InfoTooltipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="Show help"
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Info className="h-4 w-4" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{children}</TooltipContent>
    </Tooltip>
  )
}

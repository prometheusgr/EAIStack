import { useState, type FormEvent } from 'react'
import { useWorkflowsService } from '@/hooks/useWorkflowsService'
import { useIsMounted } from '@/hooks/useIsMounted'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ChatMessage } from '@/types/chat'

interface TestMessage extends ChatMessage {
  /** The version that answered, shown on every agent reply. */
  versionSequence?: number
}

interface WorkflowTestChatProps {
  workflowName: string
  version: { id: string; sequence: number }
  onClose: () => void
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : 'The test message failed.'
}

/** An admin's draft test chat (issue #84): runs one saved version end to
 * end - real tools, both guardrails, review loops - without publishing it.
 * The conversation lives only in this panel; it never appears in anyone's
 * chat history, and closing the panel ends it. */
export function WorkflowTestChat({ workflowName, version, onClose }: WorkflowTestChatProps) {
  const isMounted = useIsMounted()
  const { testChat } = useWorkflowsService()
  const [messages, setMessages] = useState<TestMessage[]>([])
  const [threadId, setThreadId] = useState<string | undefined>(undefined)
  const [inputValue, setInputValue] = useState('')
  const [sendError, setSendError] = useState<string | null>(null)

  const handleSend = async (event: FormEvent) => {
    event.preventDefault()
    const message = inputValue.trim()
    if (!message) return

    setSendError(null)
    setInputValue('')
    setMessages((prev) => [...prev, { role: 'user', text: message }])
    try {
      const reply = await testChat.mutateAsync({
        name: workflowName,
        versionId: version.id,
        message,
        threadId,
      })
      if (isMounted()) setThreadId(reply.threadId)
      if (isMounted()) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'agent',
            text: reply.response,
            sources: reply.sources,
            wasModified: reply.wasModified,
            versionSequence: reply.testVersionSequence,
          },
        ])
      }
    } catch (error) {
      if (isMounted()) setMessages((prev) => prev.slice(0, -1))
      if (isMounted()) setInputValue(message)
      if (isMounted()) setSendError(errorMessage(error))
    }
  }

  return (
    <section
      aria-label="Draft test run"
      className="space-y-3 rounded-lg border-2 border-dashed border-amber-400 p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">
            Draft test run: {workflowName} v{version.sequence}
          </h3>
          <p className="text-sm text-gray-500">
            Runs this version with real tools and guardrails. Nothing is published, and this
            conversation is not saved to anyone&apos;s chat history.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onClose}>
          End test run
        </Button>
      </div>

      <div className="space-y-2" aria-live="polite">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`rounded-lg px-3 py-2 text-sm ${
              msg.role === 'user' ? 'ml-12 bg-gray-100' : 'mr-12 border bg-white'
            }`}
          >
            <span className="text-xs font-semibold opacity-70">
              {msg.role === 'user' ? 'You' : 'Agent'}
            </span>
            {msg.role === 'agent' && (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                Draft run · v{msg.versionSequence}
              </span>
            )}
            <p className="mt-1 whitespace-pre-wrap">{msg.text}</p>
            {msg.role === 'agent' && msg.wasModified && (
              <p className="mt-1 text-xs text-gray-500">
                Part of this response was filtered by a content safety rule.
              </p>
            )}
            {msg.role === 'agent' && msg.sources && msg.sources.length > 0 && (
              <p className="mt-1 text-xs text-gray-500">
                Sources: {msg.sources.map((source) => source.title).join(', ')}
              </p>
            )}
          </div>
        ))}
        {testChat.isPending && (
          <p className="text-sm italic text-gray-500">Running the draft...</p>
        )}
      </div>

      {sendError && (
        <div
          role="alert"
          className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {sendError}
        </div>
      )}

      <form onSubmit={handleSend} className="flex gap-2">
        <Input
          aria-label="Test message"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Send a message to this version"
          disabled={testChat.isPending}
        />
        <Button type="submit" disabled={testChat.isPending || !inputValue.trim()}>
          Send
        </Button>
      </form>
    </section>
  )
}

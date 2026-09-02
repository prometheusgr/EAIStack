import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useIsMounted } from "../hooks/useIsMounted";
import { knowledgeBaseClient, type KnowledgeBase } from "../api/knowledgeBaseClient";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";

const LOAD_ERROR_MESSAGE = "Couldn't load this source document. Please try again.";

interface SourceDocumentModalProps {
  knowledgeBaseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SourceDocumentModal({
  knowledgeBaseId,
  open,
  onOpenChange,
}: SourceDocumentModalProps) {
  const { token, refreshAccessToken } = useAuth();
  const isMounted = useIsMounted();
  const [document, setDocument] = useState<KnowledgeBase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // refreshAccessToken is a new function identity on every AuthProvider
  // render (see useApiCall's apiFnRef for the same issue/fix), so it can't
  // be a useEffect dependency without re-firing this fetch on every
  // unrelated parent re-render -- e.g. every keystroke typed in the chat
  // input while this modal happens to be open. Read the latest closure
  // through a ref instead, updated every render body (not in an effect, so
  // it's current before the fetch effect below ever runs).
  const refreshAccessTokenRef = useRef(refreshAccessToken);
  refreshAccessTokenRef.current = refreshAccessToken;

  useEffect(() => {
    if (!open || !token) {
      // A missing token here is expected transiently during a token
      // refresh cycle (see AuthContext) -- wait for a real token rather
      // than surfacing a misleading "couldn't load" error for a document
      // that is actually fine.
      return;
    }
    const activeToken = token;

    // Guards against a stale response from a previous knowledgeBaseId cycle
    // landing after a newer request has started.
    let isCurrent = true;
    setDocument(null);
    setError(null);
    setIsLoading(true);

    async function load() {
      try {
        const result = await knowledgeBaseClient.get(
          knowledgeBaseId,
          activeToken,
          refreshAccessTokenRef.current
        );
        if (isCurrent && isMounted()) {
          setDocument(result);
        }
      } catch {
        if (isCurrent && isMounted()) {
          setError(LOAD_ERROR_MESSAGE);
        }
      } finally {
        if (isCurrent && isMounted()) {
          setIsLoading(false);
        }
      }
    }

    load();

    return () => {
      isCurrent = false;
    };
    // isMounted is intentionally omitted: like useApiCall's own effect, it
    // returns a fresh closure every render and is read fresh inside load()
    // when each async branch actually resumes, not at effect-schedule time.
  }, [open, knowledgeBaseId, token]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{document?.title ?? "Source document"}</DialogTitle>
        </DialogHeader>

        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading...</p>
        )}

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {document && (
          <div className="space-y-4">
            <p className="text-sm whitespace-pre-wrap">{document.content}</p>
            {document.original_filename && (
              <p className="text-xs text-muted-foreground">
                Original file: {document.original_filename}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

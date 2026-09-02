import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (!open) {
      return;
    }

    // Guards against both an unmount and a stale response from a previous
    // knowledgeBaseId/open cycle landing after a newer request has started.
    let isCurrent = true;
    setDocument(null);
    setError(null);
    setIsLoading(true);

    async function load() {
      try {
        if (!token) {
          throw new Error("No auth token available");
        }
        const result = await knowledgeBaseClient.get(knowledgeBaseId, token, refreshAccessToken);
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
  }, [open, knowledgeBaseId, token, refreshAccessToken, isMounted]);

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

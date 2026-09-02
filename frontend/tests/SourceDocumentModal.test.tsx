import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SourceDocumentModal } from "../src/components/SourceDocumentModal";
import { knowledgeBaseClient } from "../src/api/knowledgeBaseClient";
import * as AuthContext from "../src/context/AuthContext";

// Mirrors the real AuthProvider: refreshAccessToken is a plain function
// recreated on every render, not memoized with useCallback. The re-fetch
// regression this file guards against only reproduces if the mock matches
// that unstable-identity behavior instead of returning the same reference
// every call.
vi.mock("../src/context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function mockAuth(token: string | null) {
  vi.mocked(AuthContext.useAuth).mockReturnValue({
    token,
    refreshAccessToken: async () => false,
  } as ReturnType<typeof AuthContext.useAuth>);
}

vi.mock("../src/api/knowledgeBaseClient", () => ({
  knowledgeBaseClient: {
    get: vi.fn(),
  },
}));

describe("SourceDocumentModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth("fake-token-123");
  });

  it("should fetch and display the full source document content when opened", async () => {
    vi.mocked(knowledgeBaseClient.get).mockResolvedValue({
      id: "kb-1",
      user_id: "user-1",
      title: "Vacation Policy",
      content: "Employees receive 25 days of paid vacation per year.",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(
      <SourceDocumentModal
        knowledgeBaseId="kb-1"
        open={true}
        onOpenChange={() => {}}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Employees receive 25 days of paid vacation per year.")
      ).toBeInTheDocument();
    });
    expect(knowledgeBaseClient.get).toHaveBeenCalledWith(
      "kb-1",
      "fake-token-123",
      expect.any(Function)
    );
    expect(screen.getAllByText("Vacation Policy").length).toBeGreaterThan(0);
  });

  it("should show an error message when the source document fails to load", async () => {
    vi.mocked(knowledgeBaseClient.get).mockRejectedValue(new Error("Not found"));

    render(
      <SourceDocumentModal
        knowledgeBaseId="kb-missing"
        open={true}
        onOpenChange={() => {}}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/couldn.?t load/i)).toBeInTheDocument();
    });
  });

  it("should not fetch when the modal is closed", () => {
    render(
      <SourceDocumentModal
        knowledgeBaseId="kb-1"
        open={false}
        onOpenChange={() => {}}
      />
    );

    expect(knowledgeBaseClient.get).not.toHaveBeenCalled();
  });

  it("should not re-fetch on an unrelated parent re-render (open/knowledgeBaseId/token unchanged)", async () => {
    vi.mocked(knowledgeBaseClient.get).mockResolvedValue({
      id: "kb-1",
      user_id: "user-1",
      title: "Vacation Policy",
      content: "Employees receive 25 days of paid vacation per year.",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    const { rerender } = render(
      <SourceDocumentModal knowledgeBaseId="kb-1" open={true} onOpenChange={() => {}} />
    );

    await waitFor(() => {
      expect(knowledgeBaseClient.get).toHaveBeenCalledTimes(1);
    });

    // Simulates a parent re-render (e.g. typing in ChatWindow's input)
    // producing a fresh useAuth() value, exactly as the real AuthProvider
    // does -- refreshAccessToken is a new function identity every call.
    mockAuth("fake-token-123");
    rerender(
      <SourceDocumentModal knowledgeBaseId="kb-1" open={true} onOpenChange={() => {}} />
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(knowledgeBaseClient.get).toHaveBeenCalledTimes(1);
  });

  it("should wait for a token instead of showing an error when the token is transiently null", async () => {
    mockAuth(null);

    render(<SourceDocumentModal knowledgeBaseId="kb-1" open={true} onOpenChange={() => {}} />);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(knowledgeBaseClient.get).not.toHaveBeenCalled();
    expect(screen.queryByText(/couldn.?t load/i)).not.toBeInTheDocument();
  });
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SourceDocumentModal } from "../src/components/SourceDocumentModal";
import { knowledgeBaseClient } from "../src/api/knowledgeBaseClient";

vi.mock("../src/context/AuthContext", () => ({
  useAuth: () => ({
    token: "fake-token-123",
    refreshAccessToken: async () => false,
  }),
}));

vi.mock("../src/api/knowledgeBaseClient", () => ({
  knowledgeBaseClient: {
    get: vi.fn(),
  },
}));

describe("SourceDocumentModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChatWindow } from "../src/components/ChatWindow";
import * as agentsClient from "../src/api/agentsClient";

vi.mock("../src/context/AuthContext", () => ({
  useAuth: () => ({
    token: "fake-token-123",
    isAuthenticated: true,
    user: {
      name: "Test User",
    },
  }),
}));

vi.mock("../src/api/agentsClient");

describe("ChatWindow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render input field and send button", () => {
    render(<ChatWindow />);

    expect(screen.getByPlaceholderText(/message/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("should display sent message in UI", async () => {
    const mockResponse = {
      response: "Test response from agent",
      threadId: "test-thread-123",
    };

    vi.mocked(agentsClient.sendChatMessage).mockResolvedValueOnce(mockResponse);

    render(<ChatWindow />);

    const input = screen.getByPlaceholderText(/message/i);
    fireEvent.change(input, { target: { value: "Hello agent" } });

    const sendButton = screen.getByRole("button", { name: /send/i });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText("Hello agent")).toBeInTheDocument();
    });
  });

  it("should display agent response", async () => {
    const mockResponse = {
      response: "This is the agent response",
      threadId: "test-thread-456",
    };

    vi.mocked(agentsClient.sendChatMessage).mockResolvedValueOnce(mockResponse);

    render(<ChatWindow />);

    const input = screen.getByPlaceholderText(/message/i);
    fireEvent.change(input, { target: { value: "What is AI?" } });

    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("This is the agent response")).toBeInTheDocument();
    });
  });

  it("should clear input after sending", async () => {
    const mockResponse = {
      response: "Test response",
      threadId: "test-thread-789",
    };

    vi.mocked(agentsClient.sendChatMessage).mockResolvedValueOnce(mockResponse);

    render(<ChatWindow />);

    const input = screen.getByPlaceholderText(/message/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Test message" } });

    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(input.value).toBe("");
    });
  });

  it("should call sendChatMessage with token from context", async () => {
    const mockResponse = {
      response: "Test response",
      threadId: "test-thread-999",
    };

    const mockSendChat = vi
      .mocked(agentsClient.sendChatMessage)
      .mockResolvedValueOnce(mockResponse);

    render(<ChatWindow />);

    const input = screen.getByPlaceholderText(/message/i);
    fireEvent.change(input, { target: { value: "Test" } });

    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(mockSendChat).toHaveBeenCalledWith(
        "Test",
        undefined,
        "fake-token-123"
      );
    });
  });

  it("should display error state on request failure", async () => {
    vi.mocked(agentsClient.sendChatMessage).mockRejectedValueOnce(
      new Error("Network error")
    );

    render(<ChatWindow />);

    const input = screen.getByPlaceholderText(/message/i);
    fireEvent.change(input, { target: { value: "Test" } });

    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText(/error|failed/i)).toBeInTheDocument();
    });
  });
});

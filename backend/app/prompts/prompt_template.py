"""Prompt template type shared by every prompt in the library.

A single small dataclass rather than a templating engine: nothing in this
codebase yet needs variable substitution inside a prompt (chat_agent's
system prompt is static text), so building one would be a speculative
abstraction ahead of an actual second use case. Add substitution when a
concrete prompt needs it.
"""

from dataclasses import dataclass

from langchain_core.messages import SystemMessage


@dataclass(frozen=True)
class PromptTemplate:
    """A named, versioned system prompt.

    name/version exist so a prompt's history is legible in code review and
    logs (bump version when the wording changes) even though nothing yet
    reads version programmatically -- it documents intent the same way a
    migration number does, without requiring a registry to enforce it.
    """

    name: str
    version: int
    template: str

    def render(self) -> SystemMessage:
        """Return this template as a LangChain SystemMessage, ready to pass
        to an LLM invocation alongside the conversation's other messages.
        """
        return SystemMessage(content=self.template)

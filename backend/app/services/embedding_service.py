"""Service for embedding generation and management."""

import random


def generate_embedding(text: str) -> list[float]:
    """Generate a deterministic mock embedding from text.

    For MVP, we use a simple hash-based approach that's deterministic
    so the same text always produces the same embedding.

    Args:
        text: The text to generate an embedding for.

    Returns:
        A list of 1536 floating point values representing the embedding.
    """
    random.seed(hash(text) % (2**32))
    return [random.gauss(0, 0.1) for _ in range(1536)]

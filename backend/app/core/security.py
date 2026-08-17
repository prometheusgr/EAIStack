"""Security utilities for API keys and secrets."""


def mask_secret(secret: str, prefix_len: int = 6) -> str:
    """Mask a secret, keeping a small prefix visible."""
    if not secret:
        return "***..."
    if len(secret) <= prefix_len:
        return secret[0] + "***..."
    return secret[:prefix_len] + "***..."

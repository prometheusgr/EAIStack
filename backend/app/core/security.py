"""Security utilities for API keys and secrets."""


def mask_secret(secret: str) -> str:
    """
    Mask a secret, keeping a small prefix visible.

    Args:
        secret: The secret to mask

    Returns:
        Masked version showing first 6 chars + ellipsis
    """
    if not secret or len(secret) < 6:
        return secret[0:1] + "***..." if secret else "***..."

    return secret[:6] + "***..." if len(secret) > 6 else secret[0:1] + "***..."

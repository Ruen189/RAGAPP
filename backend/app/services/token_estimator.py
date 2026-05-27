class TokenEstimator:
    """Approximate tokens by characters, deterministic and fast."""

    @staticmethod
    def count(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

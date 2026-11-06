class PermanentWorkError(Exception):
    """A terminal error that must not consume retry capacity."""

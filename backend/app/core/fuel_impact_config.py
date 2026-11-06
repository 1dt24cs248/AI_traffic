"""Versioned, explicit assumptions for the commute energy scenario estimator."""

MAX_DEFAULT_EXTRA_CONSUMPTION_PERCENT = 15.0
MAX_ALLOWED_EXTRA_CONSUMPTION_PERCENT = 30.0
SPEED_BANDS = (
    (0.85, "near-free-flow"),
    (0.60, "reduced-speed"),
    (0.40, "heavy-reduction"),
)

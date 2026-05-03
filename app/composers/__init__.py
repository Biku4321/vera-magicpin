"""
Composer dispatch table.
Maps category string → category-specific compose function.
Falls back to dentist composer for unknown categories.
"""
from __future__ import annotations

from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

from app.composers import dentist, salon, restaurant, gym, pharmacy

_COMPOSERS = {
    "dentists":    dentist.compose,
    "dentist":     dentist.compose,
    "salons":      salon.compose,
    "salon":       salon.compose,
    "restaurants": restaurant.compose,
    "restaurant":  restaurant.compose,
    "gyms":        gym.compose,
    "gym":         gym.compose,
    "pharmacies":  pharmacy.compose,
    "pharmacy":    pharmacy.compose,
}


def compose(bundle: SignalBundle) -> ComposeOutput:
    """Dispatch to the right category composer based on bundle.category_id."""
    fn = _COMPOSERS.get(bundle.category_id.lower(), dentist.compose)
    return fn(bundle)

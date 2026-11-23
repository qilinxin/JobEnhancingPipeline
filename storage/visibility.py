"""Shared Job Library score and visibility rules."""

from zoneinfo import ZoneInfo

from .title_blacklist import TITLE_ALLOWED
from workflow.settings import SETTINGS

CLIENT_DELIVERY_PENALTY = int(SETTINGS["scoring"]["client_delivery_penalty"])
VISIBLE_MIN_SCORE = int(SETTINGS["scoring"]["visible_min_score"])

SYDNEY = ZoneInfo("Australia/Sydney")
DISPLAY_SCORE = f"""CASE
    WHEN c.match_score IS NOT NULL AND c.delivery_reviewed_at IS NOT NULL
         AND c.reviewed_delivery_model = 'Client delivery'
    THEN GREATEST(c.match_score - {CLIENT_DELIVERY_PENALTY}, 0)
    ELSE c.match_score
END"""
VISIBLE_CAPTURES = f"""
    c.capture_kind <> 'duplicate' AND NOT c.company_blacklisted AND NOT c.clearance_required
    AND {TITLE_ALLOWED}
    AND (c.match_score IS NULL OR ({DISPLAY_SCORE}) >= {VISIBLE_MIN_SCORE})
"""

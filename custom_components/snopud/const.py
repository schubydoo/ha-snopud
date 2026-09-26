"""Constants for the SnoPUD integration."""

from datetime import timedelta

DOMAIN = "snopud"

DEFAULT_BASE_URL = "https://my.snopud.com"
PORTAL_TIME_ZONE = "America/Los_Angeles"

# The portal publishes usage hours late, so frequent polling gains nothing.
UPDATE_INTERVAL = timedelta(hours=4)
# History to import on the first run. One request covers the whole range.
BACKFILL_DAYS = 365
# Days before the last imported hour to download again, to pick up corrections.
OVERLAP_DAYS = 3

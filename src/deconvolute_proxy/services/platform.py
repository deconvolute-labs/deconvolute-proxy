# Stub: will transmit audit events to platform API when SQLite sync is replaced
# with hosted Postgres + platform HTTP API.
#
# The SDK's TelemetrySyncWorker already handles this when DECONVOLUTE_API_KEY
# is set. This module is for additional proxy-specific platform calls:
# - fetching policy from platform API instead of local policy.yaml
# - reporting proxy health / session metadata

#pragma once

// Connects to the configured WiFi network (blocking) and then starts an SNTP
// sync so telemetry frames carry a real UTC timestamp. Returns once an IP has
// been obtained; logs and keeps retrying indefinitely on failure (no watchdog
// bailout — a collar with no network has nothing useful to fall back to).
void wifi_connect_and_sync_time(void);

// Canine CGM Bridge — hardware-bridge firmware, ESP32/ESP-IDF.
//
// Build order (see the project plan): this file currently implements Step 2 only —
// WiFi connect + a debug timer that POSTs a fake TelemetryFrame to mobile-bridge,
// proving the WiFi -> HTTP -> mobile-bridge -> cloud-backend path on real hardware
// before any Libre/Bubble sensor is in hand. Step 3 replaces send_debug_frame()'s
// fake values with real parsed readings from a Bubble/MiaoMiao BLE central
// connection (protocol pulled from xDrip+'s open-source implementation at that
// point, not fabricated here).

#include <cmath>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include "telemetry.h"
#include "wifi.h"

static const char *TAG = "main";

// STEP 2 PLACEHOLDER — remove once Step 3 wires in real Bubble/MiaoMiao BLE reads.
// Generates a slowly-varying plausible raw value so the debug frames aren't just a
// flat line, purely so it's obvious in the dashboard that live data is flowing.
static double next_debug_raw_value() {
    static double t = 0.0;
    t += 0.1;
    return 20.0 + 3.0 * std::sin(t);
}

extern "C" void app_main(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    wifi_connect_and_sync_time();

    ESP_LOGI(TAG, "starting debug telemetry loop: dog_id=%d, every %ds, target=%s",
             CONFIG_CGM_DOG_ID, CONFIG_CGM_DEBUG_FRAME_INTERVAL_SECONDS,
             CONFIG_CGM_MOBILE_BRIDGE_URL);

    while (true) {
        double raw_value = next_debug_raw_value();
        constexpr double kPlaceholderTemperatureF = 101.5;  // no real temp sensor yet
        constexpr double kPlaceholderBatteryVoltage = 3.9;  // no real battery ADC yet

        telemetry_post_frame(CONFIG_CGM_DOG_ID, raw_value, kPlaceholderTemperatureF,
                              kPlaceholderBatteryVoltage);

        vTaskDelay(pdMS_TO_TICKS(CONFIG_CGM_DEBUG_FRAME_INTERVAL_SECONDS * 1000));
    }
}

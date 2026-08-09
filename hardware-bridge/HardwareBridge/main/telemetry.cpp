#include "telemetry.h"

#include <cstdio>
#include <ctime>
#include <string>

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "telemetry";

static std::string iso8601_now_utc() {
    time_t now = time(nullptr);
    struct tm tm_utc;
    gmtime_r(&now, &tm_utc);
    char buf[32];
    // Matches Python's datetime.isoformat() on a UTC-aware datetime, e.g.
    // "2026-08-09T12:34:56+00:00" -- the exact format the simulator sends.
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+00:00", &tm_utc);
    return std::string(buf);
}

bool telemetry_post_frame(int dog_id, double raw_value, double temperature_f,
                           double battery_voltage) {
    cJSON *frame = cJSON_CreateObject();
    cJSON_AddNumberToObject(frame, "dog_id", dog_id);
    cJSON_AddStringToObject(frame, "timestamp", iso8601_now_utc().c_str());
    cJSON_AddNumberToObject(frame, "raw_value", raw_value);
    cJSON_AddNumberToObject(frame, "temperature_f", temperature_f);
    cJSON_AddNumberToObject(frame, "battery_voltage", battery_voltage);

    char *body = cJSON_PrintUnformatted(frame);
    cJSON_Delete(frame);
    if (body == nullptr) {
        ESP_LOGE(TAG, "failed to serialize telemetry frame");
        return false;
    }

    std::string url = std::string(CONFIG_CGM_MOBILE_BRIDGE_URL) + "/telemetry/frame";
    esp_http_client_config_t config = {};
    config.url = url.c_str();
    config.method = HTTP_METHOD_POST;
    config.timeout_ms = 5000;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, static_cast<int>(strlen(body)));

    esp_err_t err = esp_http_client_perform(client);
    bool ok = false;
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ok = (status >= 200 && status < 300);
        ESP_LOGI(TAG, "POST %s -> HTTP %d (%s)", url.c_str(), status, ok ? "ok" : "unexpected");
    } else {
        ESP_LOGE(TAG, "POST %s failed: %s", url.c_str(), esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    cJSON_free(body);
    return ok;
}

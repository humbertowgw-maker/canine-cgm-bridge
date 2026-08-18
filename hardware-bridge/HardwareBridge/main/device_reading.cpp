#include "device_reading.h"

#include <cstring>
#include <ctime>
#include <string>

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "device_reading";

static std::string iso8601_now_utc() {
    time_t now = time(nullptr);
    struct tm tm_utc;
    gmtime_r(&now, &tm_utc);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+00:00", &tm_utc);
    return std::string(buf);
}

bool device_reading_post(int dog_id, double glucose_mg_dl, const char *source) {
    cJSON *body_json = cJSON_CreateObject();
    cJSON_AddNumberToObject(body_json, "dog_id", dog_id);
    cJSON_AddStringToObject(body_json, "timestamp", iso8601_now_utc().c_str());
    cJSON_AddNumberToObject(body_json, "glucose_mg_dl", glucose_mg_dl);
    cJSON_AddStringToObject(body_json, "source", source);

    char *body = cJSON_PrintUnformatted(body_json);
    cJSON_Delete(body_json);
    if (body == nullptr) {
        ESP_LOGE(TAG, "failed to serialize device reading");
        return false;
    }

    std::string url = std::string(CONFIG_CGM_CLOUD_BACKEND_URL) + "/readings/device";
    esp_http_client_config_t config = {};
    config.url = url.c_str();
    config.method = HTTP_METHOD_POST;
    config.timeout_ms = 5000;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_header(client, "X-API-Key", CONFIG_CGM_CLOUD_BACKEND_API_KEY);
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

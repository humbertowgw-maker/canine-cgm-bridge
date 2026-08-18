idf_component_register(
    SRCS "main.cpp" "wifi.cpp" "telemetry.cpp" "device_reading.cpp"
         "glucose_profile.c" "ble_glucose_client.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_netif esp_event esp_http_client json bt
)

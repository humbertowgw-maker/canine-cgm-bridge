// Tier-2 BLE glucometer client: NimBLE central that scans for, connects to,
// and subscribes to the standard Bluetooth SIG Glucose Service (0x1808) on
// any nearby device advertising it — an ordinary consumer BLE glucometer,
// not a CGM. Structure (peer tracking, GAP/GATT event flow, scan-resume on
// disconnect) is adapted from ESP-IDF's own bundled NimBLE central example,
// examples/bluetooth/nimble/blecent/main/main.c — reusing a real, tested
// central implementation for the bookkeeping-heavy parts (peer.c, via the
// nimble_central_utils component) rather than writing that blind against no
// hardware. What's specific to this project: the target service/characteristic
// UUIDs, and what happens with a notification once it arrives (parse it with
// glucose_profile_parse_measurement() and forward via device_reading_post()).
#include "ble_glucose_client.h"

#include <string.h>

#include "esp_log.h"
#include "sdkconfig.h"
// NimBLE host headers must come before esp_central.h — esp_central.h's
// struct definitions (struct peer, peer_chr, peer_dsc) use types
// (ble_uuid_t, struct os_mbuf, SLIST_ENTRY, struct ble_gatt_chr/dsc/svc)
// that these headers define; getting the order backwards compiles but
// silently corrupts the struct layout the compiler sees (caught by a real
// build in this session — "'const struct peer' has no member named
// 'conn_handle'" despite the header clearly declaring it).
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "modlog/modlog.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "esp_central.h"

#include "device_reading.h"
#include "glucose_profile.h"

static const char *TAG = "ble_glucose_client";

#define GLUCOSE_SERVICE_UUID16 0x1808
#define GLUCOSE_MEASUREMENT_CHR_UUID16 0x2A18

void ble_store_config_init(void);

static int ble_glucose_gap_event(struct ble_gap_event *event, void *arg);

static void ble_glucose_scan(void) {
    uint8_t own_addr_type;
    struct ble_gap_disc_params disc_params;
    int rc;

    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "error determining address type; rc=%d", rc);
        return;
    }

    disc_params.filter_duplicates = 1;
    disc_params.passive = 1;
    disc_params.itvl = 0;
    disc_params.window = 0;
    disc_params.filter_policy = 0;
    disc_params.limited = 0;

    rc = ble_gap_disc(own_addr_type, BLE_HS_FOREVER, &disc_params, ble_glucose_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "error initiating GAP discovery; rc=%d", rc);
    }
}

// A device is worth connecting to if it advertises connectability and
// includes the Glucose Service (0x1808) in its advertised 16-bit UUIDs.
static bool ble_glucose_should_connect(const struct ble_gap_disc_desc *disc) {
    struct ble_hs_adv_fields fields;
    int rc;

    if (disc->event_type != BLE_HCI_ADV_RPT_EVTYPE_ADV_IND &&
        disc->event_type != BLE_HCI_ADV_RPT_EVTYPE_DIR_IND) {
        return false;
    }

    rc = ble_hs_adv_parse_fields(&fields, disc->data, disc->length_data);
    if (rc != 0) {
        return false;
    }

    for (int i = 0; i < fields.num_uuids16; i++) {
        if (ble_uuid_u16(&fields.uuids16[i].u) == GLUCOSE_SERVICE_UUID16) {
            return true;
        }
    }
    return false;
}

static void ble_glucose_connect_if_interesting(const struct ble_gap_disc_desc *disc) {
    uint8_t own_addr_type;
    int rc;

    if (!ble_glucose_should_connect(disc)) {
        return;
    }

    rc = ble_gap_disc_cancel();
    if (rc != 0) {
        ESP_LOGW(TAG, "failed to cancel scan before connecting; rc=%d", rc);
        return;
    }

    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "error determining address type; rc=%d", rc);
        return;
    }

    ESP_LOGI(TAG, "connecting to a device advertising the Glucose Service");
    rc = ble_gap_connect(own_addr_type, &disc->addr, 30000, NULL, ble_glucose_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "failed to connect; rc=%d", rc);
    }
}

// Called once a Glucose Measurement (0x2A18) notification arrives: copies
// the mbuf into a flat buffer, parses it, and forwards a real value to
// cloud-backend. NaN/unparseable payloads (e.g. a control-solution reading)
// are logged and dropped, not forwarded as a bogus number.
static void ble_glucose_handle_notification(const struct os_mbuf *om) {
    uint16_t len = OS_MBUF_PKTLEN(om);
    if (len == 0 || len > 32) {
        ESP_LOGW(TAG, "unexpected glucose notification length=%u", len);
        return;
    }

    uint8_t buf[32];
    int rc = os_mbuf_copydata((struct os_mbuf *)om, 0, len, buf);
    if (rc != 0) {
        ESP_LOGE(TAG, "os_mbuf_copydata failed; rc=%d", rc);
        return;
    }

    glucose_measurement_t measurement;
    if (!glucose_profile_parse_measurement(buf, len, &measurement)) {
        ESP_LOGW(TAG, "glucose notification did not parse to a usable reading (seq/NaN/short)");
        return;
    }

    ESP_LOGI(TAG, "glucometer reading: %.1f mg/dL (seq=%u, device clock %04u-%02u-%02u %02u:%02u:%02u)",
             measurement.glucose_mg_dl, measurement.sequence, measurement.year, measurement.month,
             measurement.day, measurement.hour, measurement.minute, measurement.second);

    bool ok = device_reading_post(CONFIG_CGM_DOG_ID, measurement.glucose_mg_dl, "glucometer_ble");
    if (!ok) {
        ESP_LOGE(TAG, "failed to forward glucometer reading to cloud-backend");
    }
}

static int ble_glucose_on_subscribed(uint16_t conn_handle, const struct ble_gatt_error *error,
                                      struct ble_gatt_attr *attr, void *arg) {
    (void)attr;
    (void)arg;
    if (error->status != 0) {
        ESP_LOGE(TAG, "subscribe to Glucose Measurement failed; status=%d conn_handle=%d",
                 error->status, conn_handle);
        ble_gap_terminate(conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return 0;
    }
    ESP_LOGI(TAG, "subscribed to Glucose Measurement notifications; conn_handle=%d", conn_handle);
    return 0;
}

static void ble_glucose_subscribe(const struct peer *peer) {
    const struct peer_dsc *dsc;
    uint8_t value[2] = {1, 0}; // little-endian 0x0001 == enable notifications
    int rc;

    dsc = peer_dsc_find_uuid(peer, BLE_UUID16_DECLARE(GLUCOSE_SERVICE_UUID16),
                              BLE_UUID16_DECLARE(GLUCOSE_MEASUREMENT_CHR_UUID16),
                              BLE_UUID16_DECLARE(BLE_GATT_DSC_CLT_CFG_UUID16));
    if (dsc == NULL) {
        ESP_LOGE(TAG, "peer lacks a CCCD for Glucose Measurement — can't subscribe");
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    rc = ble_gattc_write_flat(peer->conn_handle, dsc->dsc.handle, value, sizeof(value),
                               ble_glucose_on_subscribed, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "failed to write CCCD to subscribe; rc=%d", rc);
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
    }
}

static void ble_glucose_on_disc_complete(const struct peer *peer, int status, void *arg) {
    (void)arg;
    if (status != 0) {
        ESP_LOGE(TAG, "service discovery failed; status=%d conn_handle=%d", status, peer->conn_handle);
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    const struct peer_chr *chr =
        peer_chr_find_uuid(peer, BLE_UUID16_DECLARE(GLUCOSE_SERVICE_UUID16),
                            BLE_UUID16_DECLARE(GLUCOSE_MEASUREMENT_CHR_UUID16));
    if (chr == NULL) {
        ESP_LOGE(TAG, "peer advertised the Glucose Service but has no Glucose Measurement "
                      "characteristic — disconnecting");
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    ble_glucose_subscribe(peer);
}

static int ble_glucose_gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    struct ble_gap_conn_desc desc;
    int rc;

    switch (event->type) {
    case BLE_GAP_EVENT_DISC:
        ble_glucose_connect_if_interesting(&event->disc);
        return 0;

    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            rc = ble_gap_conn_find(event->connect.conn_handle, &desc);
            assert(rc == 0);
            (void)desc;

            rc = peer_add(event->connect.conn_handle);
            if (rc != 0) {
                ESP_LOGE(TAG, "failed to add peer; rc=%d", rc);
                return 0;
            }

            rc = peer_disc_all(event->connect.conn_handle, ble_glucose_on_disc_complete, NULL);
            if (rc != 0) {
                ESP_LOGE(TAG, "failed to start service discovery; rc=%d", rc);
            }
        } else {
            ESP_LOGW(TAG, "connection attempt failed; status=%d — resuming scan",
                     event->connect.status);
            ble_glucose_scan();
        }
        return 0;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "disconnected; reason=%d — resuming scan", event->disconnect.reason);
        peer_delete(event->disconnect.conn.conn_handle);
        ble_glucose_scan();
        return 0;

    case BLE_GAP_EVENT_DISC_COMPLETE:
        ESP_LOGI(TAG, "GAP discovery cycle complete; reason=%d", event->disc_complete.reason);
        return 0;

    case BLE_GAP_EVENT_NOTIFY_RX:
        ble_glucose_handle_notification(event->notify_rx.om);
        return 0;

    case BLE_GAP_EVENT_MTU:
        ESP_LOGD(TAG, "MTU update; conn_handle=%d mtu=%d", event->mtu.conn_handle, event->mtu.value);
        return 0;

    case BLE_GAP_EVENT_REPEAT_PAIRING:
        rc = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
        assert(rc == 0);
        ble_store_util_delete_peer(&desc.peer_id_addr);
        return BLE_GAP_REPEAT_PAIRING_RETRY;

    default:
        return 0;
    }
}

static void ble_glucose_on_reset(int reason) {
    ESP_LOGE(TAG, "NimBLE host reset; reason=%d", reason);
}

static void ble_glucose_on_sync(void) {
    int rc = ble_hs_util_ensure_addr(0);
    assert(rc == 0);
    ble_glucose_scan();
}

static void ble_glucose_host_task(void *param) {
    (void)param;
    ESP_LOGI(TAG, "NimBLE host task started");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void ble_glucose_client_start(void) {
    int rc = nimble_port_init();
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "failed to init NimBLE port; rc=%d", rc);
        return;
    }

    ble_hs_cfg.reset_cb = ble_glucose_on_reset;
    ble_hs_cfg.sync_cb = ble_glucose_on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    // Small bounds: we only ever care about one service (Glucose) and one
    // characteristic (Glucose Measurement) per peer, connected one at a time.
    rc = peer_init(3 /* max_peers */, 8 /* max_svcs */, 8 /* max_chrs */, 8 /* max_dscs */);
    assert(rc == 0);

    rc = ble_svc_gap_device_name_set("aegis-cgm-bridge");
    assert(rc == 0);

    ble_store_config_init();

    nimble_port_freertos_init(ble_glucose_host_task);
}

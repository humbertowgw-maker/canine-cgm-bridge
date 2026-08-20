// Tier-4 Sibionics GS1 sensor client: NimBLE central implementing the
// handshake and record-request/parse cycle documented in gs1_protocol.h.
// Structural skeleton (peer tracking, GAP/GATT event flow) reused from the
// same ESP-IDF NimBLE central example this session's Tier 2 work already
// adapted (examples/bluetooth/nimble/blecent), via the same
// nimble_central_utils component — see ble_glucose_client.c's header
// comment for why, and its include-order warning, which applies here too.
#include "gs1_sensor_client.h"

#include <string.h>
#include <time.h>

#include "esp_log.h"
#include "sdkconfig.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "modlog/modlog.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "esp_central.h"

#include "device_reading.h"
#include "gs1_protocol.h"

static const char *TAG = "gs1_sensor_client";

#define GS1_SERVICE_UUID16_BASE "0000ff30-0000-1000-8000-00805f9b34fb"

static const ble_uuid128_t gs1_service_uuid =
    BLE_UUID128_INIT(0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
                      0x00, 0x10, 0x00, 0x00, 0x30, 0xff, 0x00, 0x00);
static const ble_uuid128_t gs1_notify_chr_uuid =
    BLE_UUID128_INIT(0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
                      0x00, 0x10, 0x00, 0x00, 0x31, 0xff, 0x00, 0x00);
static const ble_uuid128_t gs1_write_chr_uuid =
    BLE_UUID128_INIT(0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
                      0x00, 0x10, 0x00, 0x00, 0x32, 0xff, 0x00, 0x00);

// Per-connection state: this firmware only ever expects one GS1 sensor
// connected at a time (single-collar-per-dog, same as Tier 2).
static uint16_t s_write_chr_val_handle;
static uint16_t s_next_ask_index;

void ble_store_config_init(void);

static int gs1_gap_event(struct ble_gap_event *event, void *arg);

static void gs1_scan(void) {
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

    rc = ble_gap_disc(own_addr_type, BLE_HS_FOREVER, &disc_params, gs1_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "error initiating GAP discovery; rc=%d", rc);
    }
}

static bool gs1_should_connect(const struct ble_gap_disc_desc *disc) {
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

    for (int i = 0; i < fields.num_uuids128; i++) {
        if (ble_uuid_cmp(&fields.uuids128[i].u, &gs1_service_uuid.u) == 0) {
            return true;
        }
    }
    return false;
}

static void gs1_connect_if_interesting(const struct ble_gap_disc_desc *disc) {
    uint8_t own_addr_type;
    int rc;

    if (!gs1_should_connect(disc)) {
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

    ESP_LOGI(TAG, "connecting to a device advertising the GS1 service");
    rc = ble_gap_connect(own_addr_type, &disc->addr, 30000, NULL, gs1_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "failed to connect; rc=%d", rc);
    }
}

// Builds the auth packet's 6-byte device-address field in Juggluco's
// reversed byte order (deviceArray(): last displayed octet first). NimBLE's
// own ble_addr_t.val is already stored least-significant-byte-first, which
// for a standard BLE address is the same convention — used directly here.
// NOT verified against a real sensor's actual expectations; if auth never
// succeeds on real hardware, this byte order is the first thing to try
// reversing.
static void gs1_send_auth(uint16_t conn_handle) {
    struct ble_gap_conn_desc desc;
    int rc = ble_gap_conn_find(conn_handle, &desc);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gap_conn_find failed; rc=%d", rc);
        return;
    }

    uint8_t auth_packet[26];
    if (!gs1_build_auth_packet(desc.peer_id_addr.val, GS1_DEFAULT_KEY_INDEX, auth_packet,
                                sizeof(auth_packet))) {
        ESP_LOGE(TAG, "gs1_build_auth_packet failed");
        return;
    }

    struct os_mbuf *om = ble_hs_mbuf_from_flat(auth_packet, sizeof(auth_packet));
    rc = ble_gattc_write_no_rsp(conn_handle, s_write_chr_val_handle, om);
    if (rc != 0) {
        ESP_LOGE(TAG, "failed to write auth packet; rc=%d", rc);
    } else {
        ESP_LOGI(TAG, "sent GS1 auth packet (key_index=%d)", GS1_DEFAULT_KEY_INDEX);
    }
}

static void gs1_send_time(uint16_t conn_handle) {
    uint8_t pkt[7];
    if (!gs1_build_time_packet((uint32_t)time(NULL), pkt, sizeof(pkt))) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat(pkt, sizeof(pkt));
    ble_gattc_write_no_rsp(conn_handle, s_write_chr_val_handle, om);
    ESP_LOGI(TAG, "sent GS1 time-sync packet");
}

static void gs1_send_activation(uint16_t conn_handle) {
    uint8_t pkt[11];
    if (!gs1_build_activation_packet((uint32_t)time(NULL), pkt, sizeof(pkt))) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat(pkt, sizeof(pkt));
    ble_gattc_write_no_rsp(conn_handle, s_write_chr_val_handle, om);
    ESP_LOGI(TAG, "sent GS1 activation packet");
}

static void gs1_send_ask_values(uint16_t conn_handle) {
    uint8_t pkt[7];
    if (!gs1_build_ask_values_packet(s_next_ask_index, pkt, sizeof(pkt))) return;
    struct os_mbuf *om = ble_hs_mbuf_from_flat(pkt, sizeof(pkt));
    ble_gattc_write_no_rsp(conn_handle, s_write_chr_val_handle, om);
    ESP_LOGI(TAG, "sent GS1 ask-values packet (index=%u)", s_next_ask_index);
}

static void gs1_handle_notification(uint16_t conn_handle, const struct os_mbuf *om) {
    uint16_t len = OS_MBUF_PKTLEN(om);
    if (len == 0 || len > 250) {
        ESP_LOGW(TAG, "unexpected GS1 notification length=%u", len);
        return;
    }

    uint8_t buf[250];
    int rc = os_mbuf_copydata((struct os_mbuf *)om, 0, len, buf);
    if (rc != 0) {
        ESP_LOGE(TAG, "os_mbuf_copydata failed; rc=%d", rc);
        return;
    }

    gs1_glucose_record_t records[16];
    gs1_dispatch_code_t dispatch = GS1_DISPATCH_NONE;
    int count = gs1_parse_notification(buf, len, records, 16, &dispatch);

    if (count < 0) {
        ESP_LOGW(TAG, "GS1 notification failed checksum/parse — dropped, not forwarded");
        return;
    }

    if (count > 0) {
        for (int i = 0; i < count; i++) {
            ESP_LOGI(TAG, "GS1 reading: %.1f mg/dL (index=%u, itime=%u)", records[i].glucose_mg_dl,
                      records[i].index, (unsigned)records[i].itime);
            bool ok = device_reading_post(CONFIG_CGM_DOG_ID, records[i].glucose_mg_dl, "gs1_direct_ble");
            if (!ok) {
                ESP_LOGE(TAG, "failed to forward GS1 reading to cloud-backend");
            }
        }
        s_next_ask_index = (uint16_t)(records[count - 1].index + 1);
        return;
    }

    switch (dispatch) {
        case GS1_DISPATCH_RETRY_AUTH:
            gs1_send_auth(conn_handle);
            break;
        case GS1_DISPATCH_SEND_TIME:
            gs1_send_time(conn_handle);
            break;
        case GS1_DISPATCH_ACTIVATE:
            gs1_send_activation(conn_handle);
            break;
        case GS1_DISPATCH_ASK_VALUES:
            gs1_send_ask_values(conn_handle);
            break;
        case GS1_DISPATCH_FATAL:
            ESP_LOGW(TAG, "GS1 protocol reported a fatal condition — disconnecting");
            ble_gap_terminate(conn_handle, BLE_ERR_REM_USER_CONN_TERM);
            break;
        case GS1_DISPATCH_NONE:
        default:
            break;
    }
}

static int gs1_on_subscribed(uint16_t conn_handle, const struct ble_gatt_error *error,
                              struct ble_gatt_attr *attr, void *arg) {
    (void)attr;
    (void)arg;
    if (error->status != 0) {
        ESP_LOGE(TAG, "subscribe to GS1 notify characteristic failed; status=%d conn_handle=%d",
                 error->status, conn_handle);
        ble_gap_terminate(conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return 0;
    }
    ESP_LOGI(TAG, "subscribed to GS1 notifications; conn_handle=%d — sending auth", conn_handle);
    s_next_ask_index = 0;
    gs1_send_auth(conn_handle);
    return 0;
}

static void gs1_subscribe(const struct peer *peer) {
    const struct peer_dsc *dsc = peer_dsc_find_uuid(
        peer, &gs1_service_uuid.u, &gs1_notify_chr_uuid.u, BLE_UUID16_DECLARE(BLE_GATT_DSC_CLT_CFG_UUID16));
    if (dsc == NULL) {
        ESP_LOGE(TAG, "peer lacks a CCCD for the GS1 notify characteristic — can't subscribe");
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    uint8_t value[2] = {1, 0};
    int rc = ble_gattc_write_flat(peer->conn_handle, dsc->dsc.handle, value, sizeof(value),
                                   gs1_on_subscribed, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "failed to write CCCD to subscribe; rc=%d", rc);
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
    }
}

static void gs1_on_disc_complete(const struct peer *peer, int status, void *arg) {
    (void)arg;
    if (status != 0) {
        ESP_LOGE(TAG, "service discovery failed; status=%d conn_handle=%d", status, peer->conn_handle);
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    const struct peer_chr *write_chr =
        peer_chr_find_uuid(peer, &gs1_service_uuid.u, &gs1_write_chr_uuid.u);
    const struct peer_chr *notify_chr =
        peer_chr_find_uuid(peer, &gs1_service_uuid.u, &gs1_notify_chr_uuid.u);
    if (write_chr == NULL || notify_chr == NULL) {
        ESP_LOGE(TAG, "peer advertised the GS1 service but is missing a characteristic — disconnecting");
        ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        return;
    }

    s_write_chr_val_handle = write_chr->chr.val_handle;
    gs1_subscribe(peer);
}

static int gs1_gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    struct ble_gap_conn_desc desc;
    int rc;

    switch (event->type) {
    case BLE_GAP_EVENT_DISC:
        gs1_connect_if_interesting(&event->disc);
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

            rc = peer_disc_all(event->connect.conn_handle, gs1_on_disc_complete, NULL);
            if (rc != 0) {
                ESP_LOGE(TAG, "failed to start service discovery; rc=%d", rc);
            }
        } else {
            ESP_LOGW(TAG, "connection attempt failed; status=%d — resuming scan",
                     event->connect.status);
            gs1_scan();
        }
        return 0;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "disconnected; reason=%d — resuming scan", event->disconnect.reason);
        peer_delete(event->disconnect.conn.conn_handle);
        gs1_scan();
        return 0;

    case BLE_GAP_EVENT_DISC_COMPLETE:
        ESP_LOGI(TAG, "GAP discovery cycle complete; reason=%d", event->disc_complete.reason);
        return 0;

    case BLE_GAP_EVENT_NOTIFY_RX:
        gs1_handle_notification(event->notify_rx.conn_handle, event->notify_rx.om);
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

static void gs1_on_reset(int reason) {
    ESP_LOGE(TAG, "NimBLE host reset; reason=%d", reason);
}

static void gs1_on_sync(void) {
    int rc = ble_hs_util_ensure_addr(0);
    assert(rc == 0);
    gs1_scan();
}

static void gs1_host_task(void *param) {
    (void)param;
    ESP_LOGI(TAG, "NimBLE host task started (GS1 sensor client)");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void gs1_sensor_client_start(void) {
    int rc = nimble_port_init();
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "failed to init NimBLE port; rc=%d", rc);
        return;
    }

    ble_hs_cfg.reset_cb = gs1_on_reset;
    ble_hs_cfg.sync_cb = gs1_on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    rc = peer_init(3 /* max_peers */, 8 /* max_svcs */, 8 /* max_chrs */, 8 /* max_dscs */);
    assert(rc == 0);

    rc = ble_svc_gap_device_name_set("aegis-cgm-bridge");
    assert(rc == 0);

    ble_store_config_init();

    nimble_port_freertos_init(gs1_host_task);
}

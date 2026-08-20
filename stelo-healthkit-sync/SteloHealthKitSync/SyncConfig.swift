import Foundation

/// Local dev config, backed by UserDefaults — no backend/keychain infra needed
/// for a utility bridge app. Same "just get it working" pattern as this
/// portfolio's other small utility apps.
enum SyncConfig {
    private static let defaults = UserDefaults.standard

    static var baseURL: String {
        // 127.0.0.1, not "localhost" — the iOS Simulator resolves "localhost"
        // to the IPv6 loopback (::1) first, which uvicorn doesn't bind by
        // default, producing a silent "Connection refused" unrelated to any
        // app logic. Confirmed via a real failed test run during development.
        get { defaults.string(forKey: "baseURL") ?? "http://127.0.0.1:9100" }
        set { defaults.set(newValue, forKey: "baseURL") }
    }

    static var apiKey: String {
        get { defaults.string(forKey: "apiKey") ?? "" }
        set { defaults.set(newValue, forKey: "apiKey") }
    }

    static var dogId: Int {
        get { defaults.integer(forKey: "dogId") == 0 ? 1 : defaults.integer(forKey: "dogId") }
        set { defaults.set(newValue, forKey: "dogId") }
    }

    static var lastSyncedAt: Date? {
        get { defaults.object(forKey: "lastSyncedAt") as? Date }
        set { defaults.set(newValue, forKey: "lastSyncedAt") }
    }
}

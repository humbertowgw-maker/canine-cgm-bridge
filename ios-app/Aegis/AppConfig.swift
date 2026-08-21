import Foundation

/// Backed by UserDefaults, same pattern as stelo-healthkit-sync's SyncConfig.
/// Defaults point at the public demo backend (synthetic "Bella" dog, seeded
/// fresh on every Railway redeploy) so the app is usable out of the box —
/// Humberto can repoint it at a private instance later for Achilles' real
/// data without a rebuild.
enum AppConfig {
    private static let defaults = UserDefaults.standard

    static var baseURL: String {
        get { defaults.string(forKey: "baseURL") ?? "https://aegis-demo-production-a33e.up.railway.app" }
        set { defaults.set(newValue, forKey: "baseURL") }
    }

    static var apiKey: String {
        get { defaults.string(forKey: "apiKey") ?? "aegis-demo-2026-view-only" }
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

import Foundation

struct DeviceReadingRequest: Encodable {
    let dog_id: Int
    let timestamp: String
    let glucose_mg_dl: Double
    let source: String
    let note: String?
}

enum APIClientError: Error {
    case badResponse(Int, String)
}

/// Posts to cloud-backend's POST /readings/device — the same endpoint the
/// ESP32 tier-2 BLE glucometer firmware uses (see hardware-bridge/HardwareBridge/main/device_reading.cpp),
/// since a HealthKit-synced Stelo sample is, like a BLE glucometer reading,
/// already a final mg/dL value with no calibration coefficient needed.
enum APIClient {
    /// The source tag for readings synced from Stelo via HealthKit. Contains
    /// "delayed" on purpose — see README for why (Dexcom syncs glucose to
    /// HealthKit/Health Connect with a fixed 3-hour delay) — so any consumer
    /// of this data (dashboard, future analytics) can recognize it as stale
    /// by string alone without needing a lookup table.
    static let steloHealthKitSource = "stelo_healthkit_delayed"

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static func postDeviceReading(dogId: Int, timestampUTC: Date, glucoseMgDl: Double) async throws {
        guard let url = URL(string: "\(SyncConfig.baseURL)/readings/device") else {
            throw APIClientError.badResponse(0, "invalid base URL")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(SyncConfig.apiKey, forHTTPHeaderField: "X-API-Key")

        let body = DeviceReadingRequest(
            dog_id: dogId,
            timestamp: isoFormatter.string(from: timestampUTC),
            glucose_mg_dl: glucoseMgDl,
            source: steloHealthKitSource,
            note: "Synced from Apple Health (Stelo) — up to 3h delayed, historical only"
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw APIClientError.badResponse(status, String(data: data, encoding: .utf8) ?? "")
        }
    }
}

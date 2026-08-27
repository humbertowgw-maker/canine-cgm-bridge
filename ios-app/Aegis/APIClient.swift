import Foundation

enum APIClientError: LocalizedError {
    case invalidURL
    case badResponse(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid backend URL"
        case .badResponse(let status, let body): return "HTTP \(status): \(body)"
        }
    }
}

/// Talks to cloud-backend's REST API -- same routes and same X-API-Key auth
/// the web dashboard (cloud-backend/static/index.html) uses. See
/// app/routers/*.py for the source of truth on every shape used here.
enum APIClient {
    private struct DogCreateRequest: Encodable {
        let name: String
        let breed: String
        let weight_kg: Double
        let target_range_low_mg_dl: Double?
        let target_range_high_mg_dl: Double?
        let feeding_schedule: [String]
    }

    private struct ManualReadingRequest: Encodable {
        let dog_id: Int
        let timestamp: String
        let glucose_mg_dl: Double
        let note: String?
    }

    private struct DeviceReadingRequest: Encodable {
        let dog_id: Int
        let timestamp: String
        let glucose_mg_dl: Double
        let source: String
        let note: String?
    }

    private struct FeedingRequest: Encodable {
        let dog_id: Int
        let timestamp: String
        let note: String?
    }

    private struct CalibrationEventRequest: Encodable {
        let reference_bg_mg_dl: Double
        let raw_value: Double
        let timestamp: String
    }

    /// Source tag for readings synced from Stelo via HealthKit -- "delayed" on
    /// purpose (Dexcom syncs to HealthKit on a fixed ~3h delay), so any
    /// consumer of this data can recognize it as stale by string alone.
    static let steloHealthKitSource = "stelo_healthkit_delayed"

    private static func request(_ path: String, method: String = "GET") throws -> URLRequest {
        guard let url = URL(string: "\(AppConfig.baseURL)\(path)") else { throw APIClientError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue(AppConfig.apiKey, forHTTPHeaderField: "X-API-Key")
        return req
    }

    private static func request<Body: Encodable>(_ path: String, method: String, body: Body) throws -> URLRequest {
        var req = try request(path, method: method)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        return req
    }

    private static func send<T: Decodable>(_ req: URLRequest, as type: T.Type) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw APIClientError.badResponse(status, String(data: data, encoding: .utf8) ?? "")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    static func fetchDogs() async throws -> [Dog] {
        try await send(try request("/dogs"), as: [Dog].self)
    }

    static func createDog(
        name: String,
        breed: String,
        weightKg: Double,
        targetLow: Double? = nil,
        targetHigh: Double? = nil,
        feedingSchedule: [String] = []
    ) async throws -> Dog {
        let body = DogCreateRequest(
            name: name,
            breed: breed,
            weight_kg: weightKg,
            target_range_low_mg_dl: targetLow,
            target_range_high_mg_dl: targetHigh,
            feeding_schedule: feedingSchedule
        )
        return try await send(try request("/dogs", method: "POST", body: body), as: Dog.self)
    }

    static func fetchReadings(dogId: Int, limit: Int = 288) async throws -> [Reading] {
        try await send(try request("/readings/\(dogId)?limit=\(limit)"), as: [Reading].self)
    }

    static func fetchLatestVelocity(dogId: Int) async throws -> Velocity {
        try await send(try request("/dogs/\(dogId)/velocity/latest"), as: Velocity.self)
    }

    static func fetchCurrentCalibration(dogId: Int) async throws -> CalibrationCoefficient {
        try await send(try request("/dogs/\(dogId)/calibration/current"), as: CalibrationCoefficient.self)
    }

    @discardableResult
    static func postManualReading(dogId: Int, glucoseMgDl: Double, timestamp: Date = Date(), note: String?) async throws -> ReadingResponse {
        let body = ManualReadingRequest(
            dog_id: dogId,
            timestamp: TimestampParser.isoOut.string(from: timestamp),
            glucose_mg_dl: glucoseMgDl,
            note: note
        )
        return try await send(try request("/readings/manual", method: "POST", body: body), as: ReadingResponse.self)
    }

    @discardableResult
    static func postDeviceReading(dogId: Int, timestampUTC: Date, glucoseMgDl: Double, source: String = steloHealthKitSource, note: String? = "Synced from Apple Health (Stelo) — up to 3h delayed, historical only") async throws -> ReadingResponse {
        let body = DeviceReadingRequest(
            dog_id: dogId,
            timestamp: TimestampParser.isoOut.string(from: timestampUTC),
            glucose_mg_dl: glucoseMgDl,
            source: source,
            note: note
        )
        return try await send(try request("/readings/device", method: "POST", body: body), as: ReadingResponse.self)
    }

    @discardableResult
    static func postFeeding(dogId: Int, timestamp: Date = Date(), note: String?) async throws -> FeedingEvent {
        let body = FeedingRequest(dog_id: dogId, timestamp: TimestampParser.isoOut.string(from: timestamp), note: note)
        return try await send(try request("/dogs/\(dogId)/feedings", method: "POST", body: body), as: FeedingEvent.self)
    }

    @discardableResult
    static func postCalibrationEvent(dogId: Int, referenceBgMgDl: Double, rawValue: Double, timestamp: Date = Date()) async throws -> CalibrationCoefficient {
        let body = CalibrationEventRequest(
            reference_bg_mg_dl: referenceBgMgDl,
            raw_value: rawValue,
            timestamp: TimestampParser.isoOut.string(from: timestamp)
        )
        return try await send(try request("/dogs/\(dogId)/calibration", method: "POST", body: body), as: CalibrationCoefficient.self)
    }
}

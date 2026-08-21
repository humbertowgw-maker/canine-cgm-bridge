import Foundation

/// cloud-backend returns naive UTC timestamps (SQLite drops tzinfo on
/// round-trip even when the value was written tz-aware) with a variable
/// fractional-seconds component -- Python's isoformat() omits it entirely
/// when microseconds == 0. Try the fractional form first, fall back to the
/// bare-seconds form.
enum TimestampParser {
    private static let withFraction: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return f
    }()
    private static let withoutFraction: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()

    static func parse(_ s: String) -> Date? {
        withFraction.date(from: s) ?? withoutFraction.date(from: s)
    }

    static let isoOut: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}

// Property names deliberately mirror the backend's snake_case JSON keys
// (see cloud-backend/app/schemas.py) rather than idiomatic Swift camelCase --
// same convention stelo-healthkit-sync's APIClient.swift already uses, kept
// consistent rather than mixing conventions across the two Aegis Swift apps.

struct Dog: Codable, Identifiable {
    let id: Int
    let name: String
    let breed: String
    let weight_kg: Double
    let target_range_low_mg_dl: Double
    let target_range_high_mg_dl: Double
    let feeding_schedule: [String]
}

struct Reading: Codable, Identifiable {
    let id: Int
    let dog_id: Int
    let timestamp: String
    let raw_value: Double?
    let temperature_f: Double?
    let estimated_glucose_mg_dl: Double
    let mobile_estimated_glucose_mg_dl: Double?
    let calibration_coefficient_id: Int?
    let source: String
    let note: String?
    let created_at: String

    var timestampDate: Date { TimestampParser.parse(timestamp) ?? Date() }
}

struct VelocityAlert: Codable, Identifiable {
    let id: Int
    let dog_id: Int
    let glucose_reading_id: Int
    let timestamp: String
    let velocity_mg_dl_per_min: Double
    let is_hypo_drop_flag: Bool
    let severity: String
    let created_at: String
}

struct ReadingResponse: Codable {
    let reading: Reading
    let alert: VelocityAlert?
}

struct CalibrationCoefficient: Codable, Identifiable {
    let id: Int
    let dog_id: Int
    let slope: Double
    let intercept: Double
    let r_squared: Double
    let point_count: Int
    let is_active: Bool
    let is_trusted: Bool
    let computed_at: String
}

struct FeedingEvent: Codable, Identifiable {
    let id: Int
    let dog_id: Int
    let timestamp: String
    let note: String?
    let created_at: String
}

struct Velocity: Codable {
    let dog_id: Int
    let velocity_mg_dl_per_min: Double?
    let as_of: String?
    let message: String?
}

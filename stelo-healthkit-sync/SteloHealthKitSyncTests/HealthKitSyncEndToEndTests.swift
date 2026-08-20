import XCTest
import HealthKit
@testable import SteloHealthKitSync

/// Real, non-interactive verification of this app's actual pipeline against a
/// locally-running cloud-backend. Requires:
///   cd cloud-backend && CGM_SHARED_SECRET=dev-secret .venv/bin/uvicorn app.main:app --port 9100
///
/// Two things are verified for real, and one thing is explicitly NOT — see
/// testFullHealthKitRoundTrip below for why.
final class HealthKitSyncEndToEndTests: XCTestCase {
    let dogId = 1
    let apiKey = "dev-secret"
    // 127.0.0.1, not "localhost" — the simulator resolves "localhost" to the
    // IPv6 loopback (::1) first, which uvicorn doesn't bind by default,
    // producing a silent "Connection refused" that has nothing to do with
    // the app's own logic. Confirmed via the exact nw_endpoint_flow_failed_with_error
    // log line naming "::1.9100" during this test's first real run.
    let baseURL = "http://127.0.0.1:9100"

    override func setUpWithError() throws {
        SyncConfig.baseURL = baseURL
        SyncConfig.apiKey = apiKey
        SyncConfig.dogId = dogId
    }

    /// Real, unconditional: posts a reading through the app's actual
    /// APIClient (same code path syncNewSamples uses) with a timestamp far in
    /// the past, and confirms both the value AND that exact original
    /// timestamp actually landed in cloud-backend — not "now". This is the
    /// part of the honesty requirement (don't silently overwrite the real
    /// HealthKit sample time with sync time) that's fully verifiable without
    /// touching HealthKit's system permission UI at all.
    func testDeviceReadingPostPreservesOriginalTimestampAndSource() async throws {
        let testValue = 133.0
        let sampleDate = Calendar.current.date(byAdding: .second, value: -1, to: Date())!
            .addingTimeInterval(-3 * 60 * 60) // 3h ago, like a real delayed Stelo sync
        try await APIClient.postDeviceReading(dogId: dogId, timestampUTC: sampleDate, glucoseMgDl: testValue)

        var request = URLRequest(url: URL(string: "\(baseURL)/readings/\(dogId)?limit=50")!)
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)

        let readings = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        let match = try XCTUnwrap(
            readings.first { ($0["estimated_glucose_mg_dl"] as? Double) == testValue },
            "posted reading not found in cloud-backend response: \(readings)"
        )
        XCTAssertEqual(match["source"] as? String, APIClient.steloHealthKitSource)

        // cloud-backend serializes naive-UTC datetimes as
        // "2026-08-20T01:48:46.672000" — no "Z"/offset, 6-digit microseconds
        // — which ISO8601DateFormatter (expects milliseconds + a timezone
        // designator) rejects outright. Parse with the backend's actual
        // format instead of assuming standard ISO 8601.
        let timestampString = try XCTUnwrap(match["timestamp"] as? String)
        let backendFormatter = DateFormatter()
        backendFormatter.locale = Locale(identifier: "en_US_POSIX")
        backendFormatter.timeZone = TimeZone(identifier: "UTC")
        backendFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        let storedTimestamp = try XCTUnwrap(
            backendFormatter.date(from: timestampString),
            "could not parse timestamp: \(timestampString)"
        )
        XCTAssertEqual(storedTimestamp.timeIntervalSince1970, sampleDate.timeIntervalSince1970, accuracy: 2.0,
                        "cloud-backend must store the real (old) sample time, not the time it was synced")
    }

    /// NOT run automatically, and this is an honest limitation, not an
    /// oversight: HKHealthStore.requestAuthorization() blocks on a real
    /// system consent sheet ("Turn On All" / "Allow") that `xcodebuild test`
    /// cannot dismiss non-interactively, and `xcrun simctl privacy` does not
    /// support pre-granting the "health" service (confirmed via
    /// `simctl privacy booted grant health ...` -> "Operation not
    /// permitted" on this machine/Xcode version — HealthKit is deliberately
    /// excluded from that mechanism, unlike camera/location/photos/etc).
    /// A prior interactive run of the app in Simulator.app, where a human
    /// taps "Turn On All" once, leaves that grant persisted in the
    /// simulator's HealthKit store across future non-interactive test runs —
    /// at that point this test will actually exercise the real
    /// inject-a-sample -> syncNewSamples() -> cloud-backend round trip. Until
    /// then it skips rather than hangs or fakes a pass.
    func testFullHealthKitRoundTrip() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw XCTSkip("HealthKit not available on this destination")
        }
        let store = HKHealthStore()
        let glucoseType = HKQuantityType(.bloodGlucose)
        let shareStatus = store.authorizationStatus(for: glucoseType)
        guard shareStatus == .sharingAuthorized else {
            throw XCTSkip("HealthKit write access not yet granted for \(glucoseType) (status: \(shareStatus.rawValue)) — run the app once in Simulator.app and tap \"Turn On All\" to grant it, then re-run this test.")
        }

        let testValue = 141.0
        let sampleDate = Date().addingTimeInterval(-3 * 60 * 60)
        try await HealthKitManager.shared.injectSyntheticSample(mgDl: testValue, at: sampleDate)

        let syncedCount = try await HealthKitManager.shared.syncNewSamples(dogId: dogId)
        XCTAssertGreaterThanOrEqual(syncedCount, 1)

        var request = URLRequest(url: URL(string: "\(baseURL)/readings/\(dogId)?limit=50")!)
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let readings = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        XCTAssertNotNil(readings.first { ($0["estimated_glucose_mg_dl"] as? Double) == testValue })
    }
}

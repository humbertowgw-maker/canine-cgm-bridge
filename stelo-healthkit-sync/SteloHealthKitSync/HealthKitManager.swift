import Foundation
import HealthKit

enum HealthKitManagerError: Error {
    case notAvailable
    case authorizationDenied
}

/// Reads blood glucose samples HealthKit has (Stelo writes these via its own
/// Apple Health sync, on a 3h delay — see README) and forwards new ones to
/// cloud-backend. Dedupes across launches/background runs using a persisted
/// HKQueryAnchor, not a timestamp cutoff, so a sample that arrives late
/// (e.g. backfilled) still gets picked up exactly once.
final class HealthKitManager {
    static let shared = HealthKitManager()

    private let store = HKHealthStore()
    private let glucoseType = HKQuantityType(.bloodGlucose)
    private let mgdlUnit = HKUnit(from: "mg/dL")
    private let anchorDefaultsKey = "steloHealthKitSync.queryAnchor"

    private init() {}

    var isHealthDataAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestAuthorization() async throws {
        guard isHealthDataAvailable else { throw HealthKitManagerError.notAvailable }
        try await store.requestAuthorization(toShare: [], read: [glucoseType])
    }

    /// DEBUG/test-only: writes a synthetic blood glucose sample into HealthKit,
    /// so the end-to-end pipeline (HealthKit -> parse -> POST -> cloud-backend)
    /// can be verified without a real Stelo sensor, the same way this repo's
    /// ESP32 firmware was proven with fake telemetry before real hardware
    /// existed. Requires share authorization, which requestAuthorization above
    /// does not request in the shipping app (read-only) — tests grant it
    /// separately via the test host's entitlements.
    func injectSyntheticSample(mgDl: Double, at date: Date) async throws {
        let quantity = HKQuantity(unit: mgdlUnit, doubleValue: mgDl)
        let sample = HKQuantitySample(type: glucoseType, quantity: quantity, start: date, end: date)
        try await store.save(sample)
    }

    /// Core sync: fetch new samples since the last persisted anchor, POST each
    /// to cloud-backend using its real HealthKit timestamp (not "now" — being
    /// honest about how old this data is is the entire point of this tier),
    /// then persist the new anchor only after every POST succeeds so a
    /// mid-sync failure doesn't silently drop samples on the next run.
    @discardableResult
    func syncNewSamples(dogId: Int = SyncConfig.dogId) async throws -> Int {
        let (samples, newAnchor) = try await fetchNewSamples()
        for sample in samples {
            let mgDl = sample.quantity.doubleValue(for: mgdlUnit)
            try await APIClient.postDeviceReading(dogId: dogId, timestampUTC: sample.startDate, glucoseMgDl: mgDl)
        }
        persistAnchor(newAnchor)
        if !samples.isEmpty {
            SyncConfig.lastSyncedAt = Date()
        }
        return samples.count
    }

    private func fetchNewSamples() async throws -> ([HKQuantitySample], HKQueryAnchor?) {
        try await withCheckedThrowingContinuation { continuation in
            let query = HKAnchoredObjectQuery(
                type: glucoseType,
                predicate: nil,
                anchor: loadAnchor(),
                limit: HKObjectQueryNoLimit
            ) { _, samplesOrNil, _, newAnchor, errorOrNil in
                if let error = errorOrNil {
                    continuation.resume(throwing: error)
                    return
                }
                let samples = (samplesOrNil as? [HKQuantitySample]) ?? []
                continuation.resume(returning: (samples, newAnchor))
            }
            store.execute(query)
        }
    }

    private func loadAnchor() -> HKQueryAnchor? {
        guard let data = UserDefaults.standard.data(forKey: anchorDefaultsKey) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    private func persistAnchor(_ anchor: HKQueryAnchor?) {
        guard let anchor,
              let data = try? NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true)
        else { return }
        UserDefaults.standard.set(data, forKey: anchorDefaultsKey)
    }
}

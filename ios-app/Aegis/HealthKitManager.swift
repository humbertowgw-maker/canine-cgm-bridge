import Foundation
import HealthKit

enum HealthKitManagerError: Error {
    case notAvailable
    case authorizationDenied
}

/// Ported from stelo-healthkit-sync/HealthKitManager.swift, same behavior:
/// reads blood glucose samples HealthKit already has (Stelo writes these via
/// its own Apple Health sync, ~3h delay) and forwards new ones to
/// cloud-backend, deduped across launches via a persisted HKQueryAnchor.
final class HealthKitManager {
    static let shared = HealthKitManager()

    private let store = HKHealthStore()
    private let glucoseType = HKQuantityType(.bloodGlucose)
    private let mgdlUnit = HKUnit(from: "mg/dL")
    private let anchorDefaultsKey = "aegis.healthkit.queryAnchor"

    private init() {}

    var isHealthDataAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestAuthorization() async throws {
        guard isHealthDataAvailable else { throw HealthKitManagerError.notAvailable }
        try await store.requestAuthorization(toShare: [], read: [glucoseType])
    }

    @discardableResult
    func syncNewSamples(dogId: Int = AppConfig.dogId) async throws -> Int {
        let (samples, newAnchor) = try await fetchNewSamples()
        for sample in samples {
            let mgDl = sample.quantity.doubleValue(for: mgdlUnit)
            try await APIClient.postDeviceReading(dogId: dogId, timestampUTC: sample.startDate, glucoseMgDl: mgDl)
        }
        persistAnchor(newAnchor)
        if !samples.isEmpty {
            AppConfig.lastSyncedAt = Date()
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

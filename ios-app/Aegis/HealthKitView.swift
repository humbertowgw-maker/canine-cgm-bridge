import SwiftUI

struct HealthKitView: View {
    @State private var status = "Not synced yet"
    @State private var isBusy = false
    @State private var authorized = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Stelo via Apple Health") {
                    Button(authorized ? "Authorized" : "Request HealthKit Authorization") {
                        Task { await requestAuth() }
                    }
                    .disabled(authorized || isBusy)

                    Button("Sync Now") {
                        Task { await syncNow() }
                    }
                    .disabled(isBusy)

                    Text(status)
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    if let last = AppConfig.lastSyncedAt {
                        Text("Last synced: \(last.formatted(date: .abbreviated, time: .shortened))")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("About") {
                    Text("Reads Stelo glucose samples that Apple Health already has (synced by the Stelo app with a fixed ~3h delay) and forwards them to your Aegis dashboard as historical readings. Not for real-time alerting — use the Log tab or a real-time sensor bridge for that.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("HealthKit sync")
        }
    }

    private func requestAuth() async {
        isBusy = true
        defer { isBusy = false }
        do {
            try await HealthKitManager.shared.requestAuthorization()
            authorized = true
            status = "Authorization requested"
        } catch {
            status = "Authorization failed: \(error.localizedDescription)"
        }
    }

    private func syncNow() async {
        isBusy = true
        defer { isBusy = false }
        do {
            let count = try await HealthKitManager.shared.syncNewSamples()
            status = "Synced \(count) new reading\(count == 1 ? "" : "s")"
        } catch {
            status = "Sync failed: \(error.localizedDescription)"
        }
    }
}

#Preview {
    HealthKitView()
}

import SwiftUI

struct ConnectView: View {
    @EnvironmentObject private var petStore: PetStore
    @StateObject private var bluetooth = BluetoothGlucoseManager()
    @State private var saveStatus: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Connect a Bluetooth meter") {
                    if let pet = petStore.selectedPet {
                        LabeledContent("Saving readings for", value: pet.name)
                    }
                    Text("Aegis scans for meters that advertise the standard Bluetooth Glucose Service. Turn on your meter, enable its Bluetooth or sync mode, and keep it near this phone.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    Button("Scan for compatible meters") { bluetooth.startScan() }
                    Text(bluetooth.stateText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    ForEach(bluetooth.meters) { meter in
                        Button {
                            bluetooth.connect(meter)
                        } label: {
                            Label("Pair \(meter.name)", systemImage: "wave.3.right")
                        }
                    }
                }

                if let reading = bluetooth.pendingReading {
                    Section("Review before saving") {
                        LabeledContent("Meter", value: reading.meterName)
                        LabeledContent("Glucose", value: String(format: "%.0f mg/dL", reading.glucoseMgDl))
                        LabeledContent("Time", value: reading.timestamp.formatted(date: .abbreviated, time: .shortened))
                        Button("Save this reading") {
                            Task { await save(reading) }
                        }
                        if let saveStatus { Text(saveStatus).font(.footnote) }
                    }
                }

                Section("Meters to look for") {
                    Text("Bluetooth-capable families include OneTouch Verio Flex/Reflect, CONTOUR NEXT ONE, and Accu-Chek Guide/Guide Me. Compatibility varies by exact model and region. If a meter does not appear in Aegis, use its official app and import through Apple Health when supported.")
                        .font(.footnote)
                    Text("Look for Bluetooth on the package and confirm the exact model supports iPhone syncing before buying.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Import readings already on this phone") {
                    HealthKitView()
                    Text("This is the preferred route for vendor apps that already write glucose readings to Apple Health. A vendor web dashboard requires a separate supported account integration; Bluetooth alone cannot access it.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("App settings") {
                    NavigationLink("Backend and dog settings") { SettingsView() }
                }
            }
            .navigationTitle("Connect")
        }
    }

    private func save(_ reading: PendingBluetoothReading) async {
        do {
            try await APIClient.postDeviceReading(
                dogId: petStore.selectedPetID,
                timestampUTC: reading.timestamp,
                glucoseMgDl: reading.glucoseMgDl,
                source: "bluetooth_sig_glucose",
                note: "Imported from \(reading.meterName); reviewed before saving"
            )
            saveStatus = "Saved to the dashboard."
            bluetooth.pendingReading = nil
        } catch {
            saveStatus = "Could not save: \(error.localizedDescription)"
        }
    }
}

#Preview {
    ConnectView()
        .environmentObject(PetStore())
}

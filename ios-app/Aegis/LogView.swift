import SwiftUI

struct LogView: View {
    private let dogId = AppConfig.dogId
    private let dogName = "your dog"

    @State private var glucoseText = ""
    @State private var glucoseNote = ""
    @State private var glucoseStatus: String?
    @State private var isLoggingGlucose = false

    @State private var feedingNote = ""
    @State private var feedingStatus: String?
    @State private var isLoggingFeeding = false

    @State private var calRefBG = ""
    @State private var calRawValue = ""
    @State private var calStatus: String?
    @State private var isLoggingCalibration = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Log a glucose reading") {
                    Text("No sensor needed — enter a glucometer reading directly. Works exactly like a sensor reading everywhere else (trend chart, hypo-drop alerts).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    TextField("Glucose (mg/dL)", text: $glucoseText)
                        .keyboardType(.decimalPad)
                    TextField("Note (optional)", text: $glucoseNote)
                    Button {
                        Task { await logGlucose() }
                    } label: {
                        if isLoggingGlucose { ProgressView() } else { Text("Log reading") }
                    }
                    .disabled(isLoggingGlucose || Double(glucoseText) == nil)
                    if let glucoseStatus {
                        Text(glucoseStatus).font(.footnote).foregroundStyle(.secondary)
                    }
                }

                Section("Log a feeding") {
                    TextField("Note (optional)", text: $feedingNote)
                    Button {
                        Task { await logFeeding() }
                    } label: {
                        if isLoggingFeeding { ProgressView() } else { Text("Log feeding") }
                    }
                    .disabled(isLoggingFeeding)
                    if let feedingStatus {
                        Text(feedingStatus).font(.footnote).foregroundStyle(.secondary)
                    }
                }

                Section("Submit a calibration point") {
                    Text("Pair a lab/reference glucose reading with the sensor's raw value at the same moment — recalculates the calibration slope/intercept.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    TextField("Reference BG (mg/dL)", text: $calRefBG)
                        .keyboardType(.decimalPad)
                    TextField("Raw sensor value", text: $calRawValue)
                        .keyboardType(.decimalPad)
                    Button {
                        Task { await logCalibration() }
                    } label: {
                        if isLoggingCalibration { ProgressView() } else { Text("Submit calibration point") }
                    }
                    .disabled(isLoggingCalibration || Double(calRefBG) == nil || Double(calRawValue) == nil)
                    if let calStatus {
                        Text(calStatus).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Log")
        }
    }

    private func logGlucose() async {
        guard let value = Double(glucoseText) else { return }
        isLoggingGlucose = true
        defer { isLoggingGlucose = false }
        do {
            let response = try await APIClient.postManualReading(
                dogId: dogId, glucoseMgDl: value, note: glucoseNote.isEmpty ? nil : glucoseNote
            )
            glucoseStatus = "Logged \(Int(value)) mg/dL"
            glucoseText = ""
            glucoseNote = ""
            if let alert = response.alert {
                await NotificationManager.requestAuthorization()
                NotificationManager.notify(alert: alert, dogName: dogName)
            }
        } catch {
            glucoseStatus = "Failed: \(error.localizedDescription)"
        }
    }

    private func logFeeding() async {
        isLoggingFeeding = true
        defer { isLoggingFeeding = false }
        do {
            _ = try await APIClient.postFeeding(dogId: dogId, note: feedingNote.isEmpty ? nil : feedingNote)
            feedingStatus = "Feeding logged"
            feedingNote = ""
        } catch {
            feedingStatus = "Failed: \(error.localizedDescription)"
        }
    }

    private func logCalibration() async {
        guard let ref = Double(calRefBG), let raw = Double(calRawValue) else { return }
        isLoggingCalibration = true
        defer { isLoggingCalibration = false }
        do {
            let coefficient = try await APIClient.postCalibrationEvent(dogId: dogId, referenceBgMgDl: ref, rawValue: raw)
            calStatus = String(format: "Calibration updated — slope %.2f, intercept %.2f, n=%d", coefficient.slope, coefficient.intercept, coefficient.point_count)
            calRefBG = ""
            calRawValue = ""
        } catch {
            calStatus = "Failed: \(error.localizedDescription)"
        }
    }
}

#Preview {
    LogView()
}

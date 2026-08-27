import SwiftUI
import Charts

struct DashboardView: View {
    @EnvironmentObject private var petStore: PetStore
    @State private var dog: Dog?
    @State private var readings: [Reading] = []
    @State private var velocity: Velocity?
    @State private var calibration: CalibrationCoefficient?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var refreshTask: Task<Void, Never>?

    private var dogId: Int { petStore.selectedPetID }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }

                    statusTiles

                    if readings.isEmpty {
                        ContentUnavailableView(
                            "No readings yet",
                            systemImage: "chart.line.uptrend.xyaxis",
                            description: Text("Pull to refresh, or check the backend URL and API key in Settings.")
                        )
                        .frame(height: 260)
                    } else {
                        chart
                    }
                }
                .padding()
            }
            .navigationTitle(dog.map { "\($0.name)'s glucose" } ?? "Glucose trend")
            .refreshable { await load() }
            .task(id: dogId) { await load() }
        }
    }

    private var statusTiles: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            tile(title: "Latest BG", value: latestBGText, tint: latestBGTint)
            tile(title: "Velocity", value: velocityText, tint: .secondary)
            tile(title: "Calibration", value: calibrationText, tint: .secondary)
            tile(title: "Last updated", value: lastUpdatedText, tint: .secondary)
        }
    }

    private func tile(title: String, value: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.bold())
                .foregroundStyle(tint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }

    private var chart: some View {
        Chart {
            if let dog {
                RectangleMark(
                    xStart: .value("Start", readings.map(\.timestampDate).min() ?? Date()),
                    xEnd: .value("End", readings.map(\.timestampDate).max() ?? Date()),
                    yStart: .value("Low", dog.target_range_low_mg_dl),
                    yEnd: .value("High", dog.target_range_high_mg_dl)
                )
                .foregroundStyle(.green.opacity(0.12))
            }
            ForEach(readings) { reading in
                LineMark(
                    x: .value("Time", reading.timestampDate),
                    y: .value("mg/dL", reading.estimated_glucose_mg_dl)
                )
                .foregroundStyle(.blue)
                .interpolationMethod(.monotone)
            }
        }
        .frame(height: 280)
        .chartYScale(domain: 20...400)
    }

    private var latestReading: Reading? { readings.max(by: { $0.timestampDate < $1.timestampDate }) }

    private var latestBGText: String {
        guard let latestReading else { return "—" }
        return String(format: "%.0f mg/dL", latestReading.estimated_glucose_mg_dl)
    }

    private var latestBGTint: Color {
        guard let latestReading, let dog else { return .primary }
        if latestReading.estimated_glucose_mg_dl < dog.target_range_low_mg_dl { return .red }
        if latestReading.estimated_glucose_mg_dl > dog.target_range_high_mg_dl { return .orange }
        return .primary
    }

    private var velocityText: String {
        guard let v = velocity?.velocity_mg_dl_per_min else { return "—" }
        return String(format: "%+.1f mg/dL/min", v)
    }

    private var calibrationText: String {
        guard let calibration else { return "Warming up" }
        return "n=\(calibration.point_count)\(calibration.is_trusted ? "" : " (untrusted)")"
    }

    private var lastUpdatedText: String {
        guard let latestReading else { return "—" }
        return latestReading.timestampDate.formatted(date: .omitted, time: .standard)
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let dogsFetch = APIClient.fetchDogs()
            async let readingsFetch = APIClient.fetchReadings(dogId: dogId)
            async let velocityFetch = try? APIClient.fetchLatestVelocity(dogId: dogId)
            async let calibrationFetch = try? APIClient.fetchCurrentCalibration(dogId: dogId)

            let dogs = try await dogsFetch
            dog = dogs.first(where: { $0.id == dogId }) ?? dogs.first
            readings = try await readingsFetch
            velocity = await velocityFetch
            calibration = await calibrationFetch
        } catch {
            errorMessage = "Couldn't load: \(error.localizedDescription)"
        }
    }
}

#Preview {
    DashboardView()
        .environmentObject(PetStore())
}

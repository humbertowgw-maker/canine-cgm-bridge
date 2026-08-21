import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            DashboardView()
                .tabItem { Label("Dashboard", systemImage: "chart.line.uptrend.xyaxis") }
            LogView()
                .tabItem { Label("Log", systemImage: "square.and.pencil") }
            HealthKitView()
                .tabItem { Label("HealthKit", systemImage: "heart.text.square") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
    }
}

#Preview {
    ContentView()
}

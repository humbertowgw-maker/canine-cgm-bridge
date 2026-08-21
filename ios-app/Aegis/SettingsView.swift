import SwiftUI

struct SettingsView: View {
    @State private var baseURL = AppConfig.baseURL
    @State private var apiKey = AppConfig.apiKey
    @State private var dogId = String(AppConfig.dogId)

    var body: some View {
        NavigationStack {
            Form {
                Section("cloud-backend") {
                    TextField("Base URL", text: $baseURL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .onChange(of: baseURL) { _, v in AppConfig.baseURL = v }
                    SecureField("X-API-Key", text: $apiKey)
                        .onChange(of: apiKey) { _, v in AppConfig.apiKey = v }
                    TextField("Dog ID", text: $dogId)
                        .keyboardType(.numberPad)
                        .onChange(of: dogId) { _, v in
                            if let n = Int(v) { AppConfig.dogId = n }
                        }
                }

                Section("About") {
                    Text("Defaults to the public Aegis demo backend — a synthetic dog seeded fresh on every deploy, safe to experiment with. Point this at a private instance to track a real dog.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
        }
    }
}

#Preview {
    SettingsView()
}

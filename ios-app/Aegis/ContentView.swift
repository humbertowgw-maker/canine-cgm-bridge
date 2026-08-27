import SwiftUI

struct ContentView: View {
    @StateObject private var petStore = PetStore()

    var body: some View {
        TabView {
            ManualHomeView()
                .tabItem { Label("Manual", systemImage: "square.and.pencil") }
            ConnectView()
                .tabItem { Label("Connect", systemImage: "dot.radiowaves.left.and.right") }
        }
        .environmentObject(petStore)
        .task { await petStore.load() }
    }
}

#Preview {
    ContentView()
}

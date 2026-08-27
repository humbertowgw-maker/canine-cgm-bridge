import SwiftUI

struct ManualHomeView: View {
    @EnvironmentObject private var petStore: PetStore
    private enum Page: String, CaseIterable, Identifiable {
        case overview = "Dashboard"
        case entry = "Enter reading"
        var id: Self { self }
    }

    @State private var page: Page = .overview
    @State private var showingAddPet = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                if petStore.pets.isEmpty {
                    Text("No pets yet")
                        .foregroundStyle(.secondary)
                } else {
                    Picker("Pet", selection: $petStore.selectedPetID) {
                        ForEach(petStore.pets) { pet in
                            Text(pet.name).tag(pet.id)
                        }
                    }
                    .pickerStyle(.menu)
                }
                Spacer()
                Button("Add Pet", systemImage: "plus") { showingAddPet = true }
            }
            .padding(.horizontal)
            .padding(.top, 8)

            Picker("Manual section", selection: $page) {
                ForEach(Page.allCases) { item in
                    Text(item.rawValue).tag(item)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 8)

            if page == .overview {
                DashboardView()
            } else {
                LogView()
            }
        }
        .sheet(isPresented: $showingAddPet) {
            AddPetView()
                .environmentObject(petStore)
        }
    }
}

#Preview {
    ManualHomeView()
        .environmentObject(PetStore())
}

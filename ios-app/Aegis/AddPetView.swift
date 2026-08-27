import SwiftUI

struct AddPetView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var petStore: PetStore

    @State private var name = ""
    @State private var breed = ""
    @State private var weight = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Animal profile") {
                    TextField("Pet's name", text: $name)
                    TextField("Breed or mix", text: $breed)
                    TextField("Weight (kg)", text: $weight)
                        .keyboardType(.decimalPad)
                }

                Section {
                    Text("Each pet gets a separate glucose history, target range, feedings, calibration, and connected-meter readings.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if let errorMessage {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }
            .navigationTitle("Add Pet")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(isSaving || name.trimmingCharacters(in: .whitespaces).isEmpty || breed.trimmingCharacters(in: .whitespaces).isEmpty || Double(weight) == nil)
                }
            }
        }
    }

    private func save() async {
        guard let weightKg = Double(weight) else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await petStore.addPet(
                name: name.trimmingCharacters(in: .whitespaces),
                breed: breed.trimmingCharacters(in: .whitespaces),
                weightKg: weightKg
            )
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

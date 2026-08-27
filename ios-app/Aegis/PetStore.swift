import Foundation

@MainActor
final class PetStore: ObservableObject {
    @Published private(set) var pets: [Dog] = []
    @Published var selectedPetID: Int {
        didSet { AppConfig.dogId = selectedPetID }
    }
    @Published private(set) var errorMessage: String?

    init() {
        selectedPetID = AppConfig.dogId
    }

    var selectedPet: Dog? {
        pets.first(where: { $0.id == selectedPetID }) ?? pets.first
    }

    func load() async {
        do {
            pets = try await APIClient.fetchDogs()
            if !pets.contains(where: { $0.id == selectedPetID }), let first = pets.first {
                selectedPetID = first.id
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func addPet(name: String, breed: String, weightKg: Double) async throws -> Dog {
        let pet = try await APIClient.createDog(name: name, breed: breed, weightKg: weightKg)
        pets.append(pet)
        selectedPetID = pet.id
        return pet
    }
}

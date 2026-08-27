import CoreBluetooth
import Foundation

struct DiscoveredGlucoseMeter: Identifiable {
    let id: UUID
    let name: String
    fileprivate let peripheral: CBPeripheral
}

struct PendingBluetoothReading: Identifiable {
    let id = UUID()
    let glucoseMgDl: Double
    let timestamp: Date
    let meterName: String
}

@MainActor
final class BluetoothGlucoseManager: NSObject, ObservableObject {
    @Published private(set) var stateText = "Bluetooth is starting…"
    @Published private(set) var meters: [DiscoveredGlucoseMeter] = []
    @Published private(set) var connectedMeterName: String?
    @Published var pendingReading: PendingBluetoothReading?

    private static let glucoseService = CBUUID(string: "1808")
    private static let glucoseMeasurement = CBUUID(string: "2A18")

    private var central: CBCentralManager!
    private var retainedPeripherals: [UUID: CBPeripheral] = [:]

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    func startScan() {
        guard central.state == .poweredOn else {
            stateText = "Turn on Bluetooth, then try again."
            return
        }
        meters.removeAll()
        retainedPeripherals.removeAll()
        stateText = "Scanning for meters using the standard Bluetooth Glucose Service…"
        central.scanForPeripherals(
            withServices: [Self.glucoseService],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
    }

    func stopScan() {
        central.stopScan()
        if meters.isEmpty { stateText = "No standard glucose meters found yet." }
    }

    func connect(_ meter: DiscoveredGlucoseMeter) {
        central.stopScan()
        meter.peripheral.delegate = self
        stateText = "Connecting to \(meter.name)…"
        central.connect(meter.peripheral)
    }

    private func decodeSFloat(_ raw: UInt16) -> Double? {
        var mantissa = Int(raw & 0x0FFF)
        var exponent = Int((raw >> 12) & 0x000F)
        if mantissa >= 0x0800 { mantissa -= 0x1000 }
        if exponent >= 0x0008 { exponent -= 0x0010 }
        if [0x07FF, 0x0800, 0x0801, 0x0802].contains(Int(raw & 0x0FFF)) { return nil }
        return Double(mantissa) * pow(10.0, Double(exponent))
    }

    private func decodeMeasurement(_ data: Data, meterName: String) -> PendingBluetoothReading? {
        let bytes = [UInt8](data)
        guard bytes.count >= 12 else { return nil }
        let flags = bytes[0]
        var index = 3 // flags + sequence number

        guard bytes.count >= index + 7 else { return nil }
        let year = Int(bytes[index]) | (Int(bytes[index + 1]) << 8)
        let components = DateComponents(
            calendar: Calendar(identifier: .gregorian),
            timeZone: .current,
            year: year,
            month: Int(bytes[index + 2]),
            day: Int(bytes[index + 3]),
            hour: Int(bytes[index + 4]),
            minute: Int(bytes[index + 5]),
            second: Int(bytes[index + 6])
        )
        index += 7

        if flags & 0x01 != 0 { index += 2 } // optional time offset
        guard flags & 0x02 != 0, bytes.count >= index + 3 else { return nil }

        let raw = UInt16(bytes[index]) | (UInt16(bytes[index + 1]) << 8)
        guard let concentration = decodeSFloat(raw) else { return nil }
        let isMolPerL = flags & 0x04 != 0
        let mgDl = isMolPerL ? concentration * 18_015.59 : concentration * 100_000.0
        guard mgDl > 0, mgDl < 1_500 else { return nil }

        return PendingBluetoothReading(
            glucoseMgDl: mgDl,
            timestamp: components.date ?? Date(),
            meterName: meterName
        )
    }
}

extension BluetoothGlucoseManager: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            switch central.state {
            case .poweredOn: stateText = "Ready to scan."
            case .poweredOff: stateText = "Bluetooth is off. Turn it on to find a meter."
            case .unauthorized: stateText = "Bluetooth permission is required to find a meter."
            case .unsupported: stateText = "Bluetooth Low Energy is not supported on this device."
            default: stateText = "Bluetooth is unavailable right now."
            }
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        Task { @MainActor in
            let name = peripheral.name
                ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String
                ?? "Glucose meter"
            retainedPeripherals[peripheral.identifier] = peripheral
            guard !meters.contains(where: { $0.id == peripheral.identifier }) else { return }
            meters.append(.init(id: peripheral.identifier, name: name, peripheral: peripheral))
            stateText = "Found \(meters.count) compatible meter\(meters.count == 1 ? "" : "s")."
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        Task { @MainActor in
            connectedMeterName = peripheral.name ?? "Glucose meter"
            stateText = "Connected. Waiting for glucose readings…"
            peripheral.discoverServices([Self.glucoseService])
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in stateText = "Connection failed: \(error?.localizedDescription ?? "unknown error")" }
    }
}

extension BluetoothGlucoseManager: CBPeripheralDelegate {
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        Task { @MainActor in
            guard error == nil else {
                stateText = "Could not read meter services."
                return
            }
            peripheral.services?.forEach {
                peripheral.discoverCharacteristics([Self.glucoseMeasurement], for: $0)
            }
        }
    }

    nonisolated func peripheral(
        _ peripheral: CBPeripheral,
        didDiscoverCharacteristicsFor service: CBService,
        error: Error?
    ) {
        Task { @MainActor in
            guard error == nil else {
                stateText = "Could not read the meter's glucose channel."
                return
            }
            service.characteristics?
                .filter { $0.uuid == Self.glucoseMeasurement }
                .forEach { peripheral.setNotifyValue(true, for: $0) }
        }
    }

    nonisolated func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        Task { @MainActor in
            guard error == nil,
                  characteristic.uuid == Self.glucoseMeasurement,
                  let data = characteristic.value,
                  let reading = decodeMeasurement(data, meterName: peripheral.name ?? "Glucose meter")
            else { return }
            pendingReading = reading
            stateText = "Reading received. Review it before saving."
        }
    }
}

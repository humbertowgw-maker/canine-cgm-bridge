import Foundation
import UserNotifications

/// Native equivalent of the web dashboard's browser Notification API stub --
/// fires a local notification when a reading's response carries a
/// VelocityAlert (see app/canine_analytics.py's hypo-drop check, returned
/// inline on every POST /readings/* response).
enum NotificationManager {
    static func requestAuthorization() async {
        _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
    }

    static func notify(alert: VelocityAlert, dogName: String) {
        let content = UNMutableNotificationContent()
        content.title = alert.severity == "critical" ? "\(dogName): critical glucose drop" : "\(dogName): hypoglycemia warning"
        content.body = String(format: "Dropping at %.1f mg/dL/min", alert.velocity_mg_dl_per_min)
        content.sound = .default

        let request = UNNotificationRequest(identifier: "alert-\(alert.id)", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}

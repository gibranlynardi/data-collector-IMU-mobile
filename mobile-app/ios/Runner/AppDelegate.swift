import UIKit
import Flutter

@UIApplicationMain
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    if let controller = window?.rootViewController as? FlutterViewController {
      let channel = FlutterMethodChannel(name: "imu_node/storage", binaryMessenger: controller.binaryMessenger)
      channel.setMethodCallHandler { call, result in
        if call.method == "getFreeStorageMb" {
          let freeMb = self.getFreeStorageMb()
          result(freeMb)
        } else {
          result(FlutterMethodNotImplemented)
        }
      }
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func getFreeStorageMb() -> Int {
    do {
      let attrs = try FileManager.default.attributesOfFileSystem(forPath: NSHomeDirectory())
      if let free = attrs[.systemFreeSize] as? NSNumber {
        return free.intValue / (1024 * 1024)
      }
    } catch {
      return -1
    }
    return -1
  }
}

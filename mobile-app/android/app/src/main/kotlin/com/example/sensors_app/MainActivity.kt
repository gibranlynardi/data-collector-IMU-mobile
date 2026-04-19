package com.example.sensors_app

import android.os.Environment
import android.os.StatFs
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity()

{
	override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
		super.configureFlutterEngine(flutterEngine)
		MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "imu_node/storage").setMethodCallHandler { call, result ->
			if (call.method == "getFreeStorageMb") {
				try {
					val path = Environment.getDataDirectory().path
					val stat = StatFs(path)
					val freeBytes = stat.availableBytes
					result.success((freeBytes / (1024 * 1024)).toInt())
				} catch (e: Exception) {
					result.error("STORAGE_ERROR", e.message, null)
				}
			} else {
				result.notImplemented()
			}
		}
	}
}

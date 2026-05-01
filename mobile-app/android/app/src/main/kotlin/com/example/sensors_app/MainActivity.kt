package com.example.sensors_app

import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.os.PowerManager
import android.os.StatFs
import android.provider.Settings
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

		MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "imu_node/runtime").setMethodCallHandler { call, result ->
			when (call.method) {
				"startForegroundMode" -> {
					try {
						val title = call.argument<String>("title") ?: "IMU Collector aktif"
						val text = call.argument<String>("text") ?: "Sampling berjalan di background"
						val intent = Intent(this, ImuForegroundService::class.java).apply {
							action = ImuForegroundService.ACTION_START
							putExtra(ImuForegroundService.EXTRA_TITLE, title)
							putExtra(ImuForegroundService.EXTRA_TEXT, text)
						}
						startForegroundService(intent)
						result.success(null)
					} catch (e: Exception) {
						result.error("FOREGROUND_START_ERROR", e.message, null)
					}
				}
				"stopForegroundMode" -> {
					try {
						val intent = Intent(this, ImuForegroundService::class.java).apply {
							action = ImuForegroundService.ACTION_STOP
						}
						startService(intent)
						result.success(null)
					} catch (e: Exception) {
						result.error("FOREGROUND_STOP_ERROR", e.message, null)
					}
				}
				"isBatteryOptimizationIgnored" -> {
					try {
						val pm = getSystemService(POWER_SERVICE) as PowerManager
						result.success(pm.isIgnoringBatteryOptimizations(packageName))
					} catch (e: Exception) {
						result.error("BATTERY_OPT_CHECK_ERROR", e.message, null)
					}
				}
				"openBatteryOptimizationSettings" -> {
					try {
						val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
							data = Uri.parse("package:$packageName")
							addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
						}
						startActivity(intent)
						result.success(null)
					} catch (e: Exception) {
						result.error("BATTERY_OPT_OPEN_ERROR", e.message, null)
					}
				}
				else -> result.notImplemented()
			}
		}
	}
}

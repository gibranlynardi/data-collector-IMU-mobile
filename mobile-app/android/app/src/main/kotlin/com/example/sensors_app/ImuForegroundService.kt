package com.example.sensors_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ImuForegroundService : Service() {
  companion object {
    const val ACTION_START = "com.example.sensors_app.action.START"
    const val ACTION_STOP = "com.example.sensors_app.action.STOP"
    const val EXTRA_TITLE = "title"
    const val EXTRA_TEXT = "text"
    private const val CHANNEL_ID = "imu_node_recording"
    private const val NOTIFICATION_ID = 21042
  }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    when (intent?.action) {
      ACTION_STOP -> {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        return START_NOT_STICKY
      }
      ACTION_START -> {
        val title = intent.getStringExtra(EXTRA_TITLE) ?: "IMU Collector aktif"
        val text = intent.getStringExtra(EXTRA_TEXT) ?: "Sampling berjalan di background"
        startForeground(NOTIFICATION_ID, buildNotification(title, text))
        return START_STICKY
      }
      else -> {
        startForeground(NOTIFICATION_ID, buildNotification("IMU Collector aktif", "Sampling berjalan di background"))
        return START_STICKY
      }
    }
  }

  private fun buildNotification(title: String, text: String): Notification {
    ensureNotificationChannel()

    val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
    val pendingIntent = PendingIntent.getActivity(
      this,
      0,
      launchIntent,
      PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    return NotificationCompat.Builder(this, CHANNEL_ID)
      .setContentTitle(title)
      .setContentText(text)
      .setSmallIcon(R.mipmap.ic_launcher)
      .setOngoing(true)
      .setCategory(NotificationCompat.CATEGORY_SERVICE)
      .setPriority(NotificationCompat.PRIORITY_DEFAULT)
      .setContentIntent(pendingIntent)
      .build()
  }

  private fun ensureNotificationChannel() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
      return
    }
    val manager = getSystemService(NotificationManager::class.java)
    val existing = manager.getNotificationChannel(CHANNEL_ID)
    if (existing != null) {
      return
    }

    val channel = NotificationChannel(
      CHANNEL_ID,
      "IMU Collector Recording",
      NotificationManager.IMPORTANCE_DEFAULT,
    )
    channel.description = "Notifikasi foreground saat sampling IMU aktif"
    manager.createNotificationChannel(channel)
  }
}

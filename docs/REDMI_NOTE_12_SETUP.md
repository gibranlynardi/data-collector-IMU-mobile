# Redmi Note 12 (MIUI / HyperOS) — Per-Phone Setup Checklist

**Why this exists:** MIUI/HyperOS aggressively freezes or kills background apps —
including active foreground services — to save power, especially when the screen is
off. On the Redmi Note 12 this is the primary cause of mid-session disconnects, not an
app bug. The IMU Node app already survives drops (buffers to disk, auto-reconnects,
backend dedups on resend — **no data is lost**), but a phone that's never been
exempted from these OS behaviors will drop far more often than necessary.

Do this **once per phone**, after installing/reinstalling the app.

---

## 1. Autostart — ON
Settings → Apps → Manage apps → **IMU Node** → **Autostart** = on.

## 2. Battery saver — No restrictions
Settings → Apps → Manage apps → **IMU Node** → **Battery saver** → **No restrictions**.

## 3. Battery-optimization exemption
Settings → Battery → App battery saver → **IMU Node** → **Don't optimize**.
(The app also prompts for this automatically on first launch — accept the dialog if
it appears. This step confirms it stuck.)

## 4. Lock the app in Recents
Open Recents (square button / swipe-up-hold) → find the **IMU Node** card → swipe down
on it → tap the **padlock** icon. This stops MIUI's memory cleaner from swiping it away.

## 5. Keep Wi-Fi on during sleep
Settings → Wi-Fi → Additional settings → **Keep Wi-Fi on during sleep** = **Always**.
This prevents Doze from dropping the Wi-Fi radio while the screen is off.

## 6. Notifications — ON
Settings → Apps → Manage apps → **IMU Node** → Notifications = on. (The app also
requests the Android 13 notification permission on first launch — accept it.) A
visible "IMU Telemetry" notification means the foreground service is alive; MIUI is
more likely to kill a service whose notification is suppressed.

## 7. Disable aggressive memory cleanup (if present)
Settings → Battery → check for "Memory extension" / "Boost speed" style features and
disable for this app, or system-wide if your MIUI version doesn't allow a per-app
exception.

## 8. Field fallback (if a specific unit still drops)
Some individual units are worse offenders even with all settings applied. If so:
record with the **screen on** (dim brightness) or the phone on a **power bank** —
either physically prevents Doze from engaging.

---

## Verification (30 seconds)

1. Apply steps 1–7 above.
2. Start a session with this phone attached.
3. Turn the phone's screen **off** and leave it untouched for **5 minutes**.
4. Confirm:
   - The dashboard keeps this device **ONLINE** the whole time.
   - The "IMU Telemetry" notification is still present when you wake the screen.
   - The recorded CSV has no gap across that window.

If it still drops after all 7 steps, use the field fallback (step 8) and note the unit
so it can be swapped or re-checked.

## Related

See `connectivity_ops_fixes_plan.md` §5 for the full analysis (why this is ~80% phone /
20% app-hygiene) and the decisive screen-off test used to confirm the cause on a given
unit.

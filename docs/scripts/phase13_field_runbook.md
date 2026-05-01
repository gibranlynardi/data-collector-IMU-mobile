# Phase 13 Field Scenario Runbook

Dokumen ini dipakai operator untuk uji lapangan butir Phase 13 secara terstruktur.

## Prasyarat

- Backend berjalan di laptop.
- Dashboard bisa diakses.
- 3 phone atau simulator aktif.
- Webcam terpasang.

## Skenario

1. Start dengan 3 device online:
- Jalankan simulator: `python scripts/phase13_device_simulator.py --duration-seconds 30`
- Verifikasi dashboard menunjukkan 3 device online.

2. Matikan Wi-Fi salah satu phone saat recording:
- Untuk simulator: observe device THIGH disconnect otomatis.
- Verifikasi event offline muncul di dashboard.

3. Nyalakan lagi dan backlog sync:
- Verifikasi device reconnect dan ACK bertambah.
- Verifikasi `duplicate_batches`/`last_received_seq` naik sesuai reconnect.

4. Refresh dashboard saat annotation aktif:
- Buat annotation aktif, refresh dashboard.
- Verifikasi annotation masih muncul.

5. Restart backend saat recording:
- Restart proses backend.
- Verifikasi device reconnect dan lanjut upload backlog.

6. Cabut webcam sebelum start:
- Start session tanpa override harus gagal.

7. Cabut webcam saat recording:
- Verifikasi warning webcam gagal di dashboard.

8. Storage laptop hampir penuh:
- Turunkan threshold storage runtime di env.
- Verifikasi warning/critical event muncul.

9. Session end saat phone offline:
- Stop session saat satu device offline.
- Verifikasi status `SYNCING` lalu `INCOMPLETE_FINALIZED`/`COMPLETED` sesuai kondisi.

10. Upload manual ke FAMS:
- Jalankan `scripts/upload_to_fams.ps1` atau `scripts/upload_to_fams.sh`.
- Verifikasi checksum lokal/remote match.
- Panggil endpoint mark uploaded.

# Operator Guide (LAN Laptop Deployment)

Panduan ini menutup kebutuhan operator untuk Phase 14.

## 1) Connect phone ke Wi-Fi LAN yang sama

1. Pastikan laptop dan semua phone berada di SSID Wi-Fi yang sama.
2. Cek IP laptop dari terminal:
   - `ipconfig`
3. Catat alamat IPv4 laptop, contoh `192.168.1.10`.

## 2) Set backend IP di mobile app

1. Buka app mobile node.
2. Isi backend URL dengan IP laptop:
   - `http://<IP_LAPTOP>:8000`
3. Pilih role device (chest/waist/thigh).
4. Simpan konfigurasi.

## 3) Jalankan backend + dashboard

### Native (direkomendasikan untuk webcam)

1. Jalankan:
   - `powershell -ExecutionPolicy Bypass -File scripts/start_all.ps1`
2. Dashboard tersedia di:
   - `http://127.0.0.1:3000`
3. Backend health di:
   - `http://127.0.0.1:8000/health`

### Docker Compose

1. Copy env template:
   - `Copy-Item .env.example .env`
2. Jalankan:
   - `docker compose up -d --build`
3. Jika butuh PostgreSQL container:
   - `docker compose --profile database up -d --build`

## 4) Preflight sebelum recording

1. Buka dashboard.
2. Pastikan checklist preflight hijau:
   - backend healthy
   - storage writable dan cukup
   - webcam tersedia
   - semua device required online
   - battery/storage phone aman
   - clock sync quality OK

## 5) Start/Stop session

1. Klik create session.
2. Assign device ke session bila perlu.
3. Klik start session.
4. Saat selesai pengambilan data, klik stop session.
5. Finalize session sesuai kondisi:
   - complete bila semua data lengkap
   - incomplete finalize dengan alasan bila ada kegagalan permanen

## 6) Buat annotation

1. Pilih label aktivitas.
2. Klik start annotation saat aktivitas mulai.
3. Klik stop annotation saat aktivitas selesai.
4. Gunakan edit/delete bila perlu koreksi.

## 7) Verifikasi video

1. Cek panel video status di dashboard.
2. Setelah stop session, cek artifact video:
   - `sessions/{session_id}/video/{session_id}_webcam.mp4`
   - `sessions/{session_id}/video/{session_id}_webcam.json`
3. Pastikan sidecar metadata berisi durasi, frame_count, dan status valid.

## 8) Export dataset

1. Finalize session.
2. Pastikan export ZIP tersedia:
   - `sessions/{session_id}/export/{session_id}_dataset.zip`
3. Cek manifest dan artifact list dari dashboard.

## 9) Upload manual ke FAMS

1. Siapkan env FAMS di `.env` atau backend env:
   - `FAMS_HOST`, `FAMS_USER`, `FAMS_REMOTE_PATH`, `FAMS_SSH_KEY_PATH`
2. Jalankan script upload:
   - `scripts/upload_to_fams.ps1 -ArchivePath <path_zip>`
3. Verifikasi checksum lokal dan remote sesuai.
4. Klik `Mark as uploaded` dari dashboard/API.

## 10) Recovery saat device gagal

1. Jika phone offline saat recording:
   - biarkan phone tetap recording lokal
   - tunggu reconnect
   - backend akan sync backlog
2. Jika dashboard refresh/tertutup:
   - buka lagi dashboard, state session akan dipulihkan
3. Jika backend restart:
   - jalankan backend lagi
   - phone reconnect dan kirim pending data
4. Jika webcam gagal:
   - cek warning dashboard
   - tentukan lanjut atau stop sesuai SOP

## Catatan Webcam di Deployment

- Native backend di laptop paling stabil untuk akses webcam.
- Docker untuk backend tidak direkomendasikan saat membutuhkan webcam hardware langsung di Windows, karena device mapping webcam membutuhkan setup khusus host/driver.

# Phase 15 Hardening Runbook

Dokumen ini mencatat hardening deployment setelah Phase 14.

## 1) Log rotation container

`docker-compose.yml` sudah mengaktifkan log rotation untuk semua service:

- driver: `json-file`
- `max-size: 10m`
- `max-file: 5`

Dampak:
- log container tidak tumbuh tak terbatas.
- konsumsi disk lebih terkontrol saat service berjalan lama.

## 2) Restart dan graceful shutdown tuning

`docker-compose.yml` sudah menambahkan:

- `restart: unless-stopped`
- `init: true`
- `stop_grace_period` per service
- healthcheck backend dan dashboard
- dashboard menunggu backend healthy sebelum start

Dampak:
- startup lebih tertib.
- shutdown lebih aman (proses punya waktu flush/cleanup).

## 3) Backup data otomatis

Script backup:
- `scripts/backup_data.ps1`

Fitur:
- backup konten `data/sessions`
- copy `data/metadata.db` best effort (jika sedang lock, backup tetap jalan)
- output ZIP ke folder `backups`
- retention cleanup berdasarkan hari

Konfigurasi env (`.env`):
- `BACKUP_SOURCE_DIR` (default `./data`)
- `BACKUP_OUTPUT_DIR` (default `./backups`)
- `BACKUP_RETENTION_DAYS` (default `14`)

## 4) Schedule backup harian (Windows)

Helper script:
- `scripts/setup_backup_task.ps1`

Contoh:
- `powershell -ExecutionPolicy Bypass -File scripts/setup_backup_task.ps1 -TaskName IMUCollectorDailyBackup -RunAt 02:00`

Ini akan mendaftarkan Windows Scheduled Task yang menjalankan backup harian.

## 5) Verifikasi cepat

1. Jalankan stack (native atau docker).
2. Jalankan manual backup sekali:
   - `powershell -ExecutionPolicy Bypass -File scripts/backup_data.ps1`
3. Pastikan file ZIP baru muncul di folder `backups`.
4. Cek log service docker:
   - `docker compose logs backend --tail=100`

## Catatan Operasional

- Untuk sesi recording aktif, backup tetap berjalan tanpa gagal total meski `metadata.db` sedang lock.
- Jika ingin snapshot database yang konsisten 100 persen, lakukan backup saat service backend dalam keadaan stop/maintenance.

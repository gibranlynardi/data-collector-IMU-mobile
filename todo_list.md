Siap. Ini TODO list arsitektur yang bisa dipakai sebagai roadmap implementasi. Aku susun dari fondasi dulu sampai sistemnya tahan failure.

**Phase 0: Keputusan Desain**
- [x] Tetapkan stack final:
  - [x] Mobile: Flutter
  - [x] Backend: FastAPI
  - [x] Frontend: Next.js
  - [x] Database: PostgreSQL
  - [x] Time-series: TimescaleDB atau PostgreSQL biasa dulu
- [x] Tentukan format ID:
  - [x] `device_id` (DEVICE-{name of device-00{increment value start 1}})
  - [x] `session_id` (timestamp-uuid-device-id)
  - [x] `annotation_id`
- [x] Tentukan sampling rate default, misalnya `100 Hz` -> fleksible
- [x] Tentukan jumlah device wajib per session, misalnya `3 HP` -> fleksible tergantung banyaknya device yang terconnect
- [x] Tentukan format export dataset final (bisa semua, seperti csv, excel, json, parquet)

**Phase 1: Backend Foundation**
- [ ] Buat project FastAPI
- [ ] Setup PostgreSQL database
- [ ] Setup migration tool, misalnya Alembic
- [ ] Buat tabel `devices`
- [ ] Buat tabel `sessions`
- [ ] Buat tabel `session_devices`
- [ ] Buat tabel `sensor_samples`
- [ ] Buat tabel `annotations`
- [ ] Tambahkan unique constraint:
  ```sql
  UNIQUE(session_id, device_id, seq)
  ```
- [ ] Buat model Pydantic untuk:
  - [ ] device registration
  - [ ] session create/start/end
  - [ ] sensor sample
  - [ ] batch upload
  - [ ] annotation start/end
- [ ] Buat REST endpoint device:
  - [ ] `POST /devices/register`
  - [ ] `GET /devices`
  - [ ] `PATCH /devices/{device_id}`
- [ ] Buat REST endpoint session:
  - [ ] `POST /sessions`
  - [ ] `POST /sessions/{session_id}/start`
  - [ ] `POST /sessions/{session_id}/end`
  - [ ] `GET /sessions/{session_id}`
  - [ ] `GET /sessions/{session_id}/status`
- [ ] Buat REST endpoint annotation:
  - [ ] `POST /sessions/{session_id}/annotations/start`
  - [ ] `POST /sessions/{session_id}/annotations/{annotation_id}/end`
  - [ ] `GET /sessions/{session_id}/annotations`
  - [ ] `PATCH /annotations/{annotation_id}`
  - [ ] `DELETE /annotations/{annotation_id}`
- [ ] Buat REST endpoint upload batch:
  - [ ] `POST /sessions/{session_id}/devices/{device_id}/samples/batch`
- [ ] Pastikan batch upload idempotent:
  - [ ] duplicate sample tidak bikin error fatal
  - [ ] duplicate sample tidak tersimpan dua kali
  - [ ] response memberi info `accepted`, `duplicate_count`, `last_received_seq`

**Phase 2: WebSocket Backend**
- [ ] Buat WebSocket untuk device:
  ```text
  /ws/device/{device_id}
  ```
- [ ] Buat WebSocket untuk dashboard:
  ```text
  /ws/dashboard/{session_id}
  ```
- [ ] Implement device heartbeat:
  - [ ] `device_id`
  - [ ] `session_id`
  - [ ] `recording`
  - [ ] `local_last_seq`
  - [ ] `uploaded_last_seq`
  - [ ] `pending_samples`
  - [ ] `battery`
  - [ ] `storage_free_mb`
- [ ] Implement command broadcast dari backend ke HP:
  - [ ] `START_SESSION`
  - [ ] `STOP_SESSION`
  - [ ] `SYNC_REQUIRED`
  - [ ] `PING`
- [ ] Implement realtime sensor forwarding ke dashboard
- [ ] Implement status forwarding ke dashboard
- [ ] Implement reconnect handshake:
  - [ ] HP kirim `DEVICE_RECONNECT`
  - [ ] backend balas `backend_last_seq`
  - [ ] HP upload missing samples
- [ ] Implement timeout device:
  - [ ] kalau heartbeat hilang, status jadi `offline`
  - [ ] simpan `last_seen`

**Phase 3: Flutter App Refactor**
- [ ] Tambahkan dependency Flutter:
  - [ ] `web_socket_channel`
  - [ ] `sqflite`
  - [ ] `path_provider`
  - [ ] `uuid`
  - [ ] optional: `battery_plus`
  - [ ] optional: `connectivity_plus`
- [ ] Buat device setup screen:
  - [ ] input device name
  - [ ] input/select location ID
  - [ ] simpan `device_id` lokal
  - [ ] register device ke backend
- [ ] Buat backend connection manager:
  - [ ] connect WebSocket
  - [ ] auto reconnect
  - [ ] exponential backoff
  - [ ] heartbeat
  - [ ] receive command dari backend
- [ ] Buat local database SQLite:
  - [ ] tabel `local_sessions`
  - [ ] tabel `sensor_samples`
  - [ ] tabel `upload_batches`
- [ ] Ubah recorder supaya selalu tulis lokal dulu:
  - [ ] setiap sample punya `seq`
  - [ ] setiap sample punya `timestamp_device`
  - [ ] setiap sample punya `elapsed_ms`
  - [ ] setiap sample punya `uploaded = false`
- [ ] Implement session command handler:
  - [ ] saat `START_SESSION`, mulai recording lokal
  - [ ] saat `STOP_SESSION`, stop recording lokal
  - [ ] jika offline, tetap record sampai dapat stop lokal/manual recovery
- [ ] Implement batch uploader:
  - [ ] ambil sample `uploaded = false`
  - [ ] upload per batch, misalnya 250-1000 samples
  - [ ] mark uploaded setelah backend sukses
  - [ ] retry kalau gagal
- [ ] Implement recovery setelah app crash:
  - [ ] cek `local_sessions` yang statusnya `recording`
  - [ ] tampilkan status `Recovered unfinished session`
  - [ ] lanjut upload data yang belum terkirim
- [ ] Tambahkan UI status di HP:
  - [ ] connected/offline
  - [ ] recording/not recording
  - [ ] current session
  - [ ] local samples
  - [ ] pending upload
  - [ ] last sync
  - [ ] storage warning
- [ ] Tetap pertahankan fallback export CSV lokal kalau dibutuhkan

**Phase 4: Web Dashboard**
- [ ] Buat project frontend
- [ ] Buat halaman session dashboard
- [ ] Buat panel session control:
  - [ ] create session
  - [ ] start session
  - [ ] end session
  - [ ] finalize session
- [ ] Buat device health panel:
  - [ ] online/offline
  - [ ] recording status
  - [ ] last seen
  - [ ] sample count
  - [ ] pending samples
  - [ ] battery
  - [ ] storage
  - [ ] effective sampling rate
- [ ] Buat realtime graph:
  - [ ] per device/location
  - [ ] accelerometer x/y/z
  - [ ] gyroscope x/y/z
  - [ ] rolling window, misalnya 10-30 detik
- [ ] Buat annotation control:
  - [ ] pilih label
  - [ ] start annotation
  - [ ] end annotation
  - [ ] notes optional
- [ ] Buat annotation list:
  - [ ] label
  - [ ] start time
  - [ ] end time
  - [ ] duration
  - [ ] edit
  - [ ] delete
- [ ] Tambahkan active annotation recovery:
  - [ ] kalau web refresh, annotation aktif tetap muncul
- [ ] Buat session sync status:
  - [ ] completed
  - [ ] syncing
  - [ ] incomplete
  - [ ] finalized with missing data
- [ ] Tambahkan warning UI:
  - [ ] device offline
  - [ ] missing sequence
  - [ ] sampling rate drop
  - [ ] pending upload besar
  - [ ] device storage rendah

**Phase 5: Time Synchronization**
- [ ] Simpan tiga jenis waktu pada sample:
  - [ ] `timestamp_device`
  - [ ] `timestamp_server_received`
  - [ ] `elapsed_ms`
- [ ] Saat session start, backend kirim:
  - [ ] `server_start_time`
  - [ ] `session_id`
- [ ] HP simpan:
  - [ ] `device_start_time`
  - [ ] `monotonic_start_ms`
- [ ] Backend hitung estimasi waktu sample:
  ```text
  estimated_server_time = server_start_time + elapsed_ms
  ```
- [ ] Tambahkan ping/pong time sync:
  - [ ] backend kirim ping time
  - [ ] HP balas pong
  - [ ] backend estimasi latency dan offset
- [ ] Simpan `clock_offset_ms` per device/session
- [ ] Tentukan waktu utama untuk annotation join:
  - [ ] MVP: `estimated_server_time`
  - [ ] fallback: `timestamp_server_received`

**Phase 6: Dataset Export**
- [ ] Buat endpoint export:
  ```text
  GET /sessions/{session_id}/export.csv
  ```
- [ ] Buat export per device
- [ ] Buat export gabungan semua device
- [ ] Join sensor sample dengan annotation:
  ```sql
  sample_time BETWEEN annotation.start_time AND annotation.end_time
  ```
- [ ] Tentukan format CSV final:
  ```text
  timestamp,session_id,device_id,location_id,acc_x_g,acc_y_g,acc_z_g,gyro_x_deg,gyro_y_deg,gyro_z_deg,label
  ```
- [ ] Tambahkan opsi export:
  - [ ] raw without label
  - [ ] labeled only
  - [ ] include unlabeled as `null`
  - [ ] per annotation segment
- [ ] Tambahkan manifest export:
  - [ ] session metadata
  - [ ] device list
  - [ ] annotation list
  - [ ] missing data report

**Phase 7: Failure Handling**
- [ ] Tangani web disconnect:
  - [ ] recording tetap jalan
  - [ ] web reconnect ambil session state terbaru
- [ ] Tangani backend restart:
  - [ ] HP tetap recording lokal
  - [ ] HP reconnect otomatis
  - [ ] HP upload backlog
- [ ] Tangani HP network disconnect:
  - [ ] HP tetap recording lokal
  - [ ] backend tandai device offline
  - [ ] backlog upload setelah reconnect
- [ ] Tangani HP app crash:
  - [ ] SQLite tetap menyimpan data
  - [ ] recovery unfinished session
  - [ ] upload pending data
- [ ] Tangani baterai habis:
  - [ ] backend tandai device lost
  - [ ] data sebelum mati tetap bisa diupload nanti
- [ ] Tangani storage penuh:
  - [ ] HP beri warning
  - [ ] stop aman jika storage kritis
  - [ ] backend/web tampilkan warning
- [ ] Tangani duplicate upload:
  - [ ] unique constraint
  - [ ] idempotent batch endpoint
- [ ] Tangani missing sample:
  - [ ] deteksi gap berdasarkan `seq`
  - [ ] tampilkan di session report
- [ ] Tangani annotation lupa di-end:
  - [ ] web tampilkan active annotation
  - [ ] backend bisa auto-close saat session ended, dengan warning
- [ ] Tangani session end saat device offline:
  - [ ] session masuk status `SYNCING`
  - [ ] tunggu device reconnect
  - [ ] opsi finalize incomplete

**Phase 8: Session Finalization**
- [ ] Setelah `End Session`, ubah status ke `ENDING`
- [ ] Backend kirim `STOP_SESSION` ke device online
- [ ] Device stop recording dan upload pending samples
- [ ] Backend cek completeness:
  - [ ] last seq per device
  - [ ] gap sequence
  - [ ] sample count expected vs actual
  - [ ] annotation completeness
- [ ] Jika lengkap, status jadi `COMPLETED`
- [ ] Jika belum lengkap, status jadi `SYNCING`
- [ ] Jika device gagal total, operator bisa pilih:
  - [ ] wait for sync
  - [ ] mark device failed
  - [ ] finalize incomplete
- [ ] Simpan finalization report
- [ ] Tampilkan readiness export di dashboard

**Phase 9: Monitoring & QA**
- [ ] Tambahkan backend logging
- [ ] Tambahkan error tracking
- [ ] Tambahkan metrics:
  - [ ] samples per second per device
  - [ ] dropped/gap samples
  - [ ] websocket reconnect count
  - [ ] upload retry count
  - [ ] pending samples
- [ ] Buat simulator device untuk testing tanpa 3 HP
- [ ] Buat test backend:
  - [ ] batch upload idempotent
  - [ ] duplicate handling
  - [ ] missing seq detection
  - [ ] annotation interval
  - [ ] session state machine
- [ ] Buat test Flutter local persistence
- [ ] Buat test reconnect sync
- [ ] Buat test export CSV
- [ ] Uji skenario nyata:
  - [ ] matikan Wi-Fi HP saat recording
  - [ ] restart backend saat recording
  - [ ] refresh web saat annotation aktif
  - [ ] kill app HP lalu buka lagi
  - [ ] upload batch duplicate
  - [ ] session end saat salah satu HP offline

**Phase 10: Deployment**
- [ ] Buat Docker Compose:
  - [ ] backend
  - [ ] PostgreSQL/TimescaleDB
  - [ ] frontend
- [ ] Setup environment config:
  - [ ] backend URL
  - [ ] database URL
  - [ ] WebSocket URL
- [ ] Setup backup database
- [ ] Setup export storage folder
- [ ] Setup basic auth/user login jika dibutuhkan
- [ ] Setup LAN deployment untuk lab
- [ ] Dokumentasi cara menjalankan:
  - [ ] backend
  - [ ] frontend
  - [ ] mobile app
  - [ ] flow data collection
  - [ ] recovery saat failure

**Urutan Paling Recommended**
Kalau mau mulai coding tanpa bingung, urutan praktisnya:

1. Backend FastAPI + database schema
2. WebSocket device connection
3. Flutter connect ke backend dan stream data
4. Web dashboard realtime graph
5. Session start/end dari web
6. Annotation start/end dari web
7. Local SQLite buffer di HP
8. Batch upload dan reconnect sync
9. Session finalization
10. Export dataset CSV

Intinya MVP dulu harus bisa:

```text
3 HP connect -> web klik start -> data masuk backend -> grafik muncul -> annotation dibuat -> web klik end -> export CSV
```

Setelah itu baru dibuat tahan banting:

```text
offline buffer -> reconnect sync -> missing data report -> finalize safely
```
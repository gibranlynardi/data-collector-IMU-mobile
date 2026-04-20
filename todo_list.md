# TODO List: Multi-Phone IMU Collector + Synchronized Webcam Recording

Roadmap ini mengikuti arsitektur terbaru:

- 3+ Android phone sebagai mobile IMU nodes.
- Tiap phone mengirim data IMU ke laptop lewat Wi-Fi LAN.
- Payload utama pakai Protobuf, target sampling `100 Hz`.
- Laptop menjalankan backend FastAPI, dashboard browser, webcam recorder, dan local SSD storage.
- Dashboard mengontrol `START / STOP / LABEL`, preflight checklist, realtime graph, dan list annotation.
- Backend menulis CSV per device dan metadata session.
- Webcam direkam otomatis saat session berjalan supaya video sinkron dengan data sensor.
- Setelah session selesai, dataset diupload manual via SSH ke FAMS Server archive.

---

## Phase 0: Finalisasi Scope dan Konvensi

- [x] Tetapkan topologi utama:
  - [x] Mobile nodes: minimal 3 Android phone.
  - [x] Posisi awal device: `chest`, `waist`, `thigh`.
  - [x] Backend: FastAPI di laptop.
  - [x] Frontend: dashboard browser di laptop.
  - [x] Network: Wi-Fi LAN lokal.
  - [x] Storage: SSD laptop untuk CSV + video.
  - [x] Archive: FAMS Server via manual SSH upload.
- [x] Tetapkan data rate:
  - [x] IMU target `100 Hz` per phone.
  - [x] Payload sensor memakai Protobuf.
- [x] Tetapkan format ID:
  - [x] `device_id`, format final: `DEVICE-{ROLE}-{NNN}` (contoh: `DEVICE-CHEST-001`).
  - [x] `session_id`, format final: `YYYYMMDD_HHMMSS_{8HEX}` (contoh: `20260419_143022_A1B2C3D4`).
  - [x] `annotation_id`, format final: `ANN-{session_id}-{NNNN}`.
  - [x] `video_id`, format final: `VID-{session_id}-WEBCAM-01`.
- [x] Tetapkan device roles:
  - [x] `chest`.
  - [x] `waist`.
  - [x] `thigh`.
  - [x] `other`.
- [x] Tetapkan label aktivitas/anotasi (ini flexible dulu nanti bisa diinput lewat web):
  - [x] format label: `domain.activity.variant` (contoh: `adl.walk.normal`, `transition.sit_to_stand.default`).
  - [x] daftar label awal: `adl.walk.normal`, `adl.stand.still`, `adl.sit.still`, `transition.sit_to_stand.default`, `transition.stand_to_sit.default`, `event.fall_simulation.forward`.
  - [x] boleh edit label setelah recording dengan audit trail (menyimpan nilai sebelum/sesudah + waktu edit).
- [x] Tetapkan struktur folder dataset final di SSD.
  - [x] Root final: `DATA_ROOT/sessions/{session_id}/`.
  - [x] Subfolder final: `sensor/`, `video/`, `logs/`, `export/`.
  - [x] Metadata final minimal: `manifest.json`, `session.json`, `devices.json`, `annotations.csv`, `sync_report.json`, `preflight_report.json`.
- [x] Tetapkan aturan session:
  - [x] session boleh start hanya setelah preflight pass.
  - [x] session end harus menutup sensor recording, annotation aktif, dan video recording.
  - [x] session baru tidak boleh dibuat jika session sebelumnya belum finalized/saved.

### Phase 0 Decision Notes (Final)

- Semua identifier menggunakan huruf kapital, angka, dan separator `-` atau `_`, tanpa spasi.
- `ROLE` valid untuk `device_id` adalah `CHEST`, `WAIST`, `THIGH`, `OTHER`.
- Nomor urut memakai zero-padding: `NNN` untuk device, `NNNN` untuk annotation.
- Session dengan status `ENDING` atau `SYNCING` dianggap belum selesai dan memblokir pembuatan session baru.
- Finalisasi struktur folder rinci tetap mengikuti Phase 9; keputusan di Phase 0 ini adalah baseline yang wajib konsisten.
- Audit trail annotation sudah mulai diimplementasikan di backend (`annotation_audits`) untuk operasi patch/stop/delete label timeline.

---

## Phase 1: Protobuf Contract

- [x] Buat folder kontrak Protobuf, misalnya `proto/`.
- [x] Buat `sensor_sample.proto`.
- [x] Definisikan message `SensorSample`:
  - [x] `session_id`.
  - [x] `device_id`.
  - [x] `device_role`.
  - [x] `seq`.
  - [x] `timestamp_device_unix_ns`.
  - [x] `elapsed_ms`.
  - [x] `acc_x_g`.
  - [x] `acc_y_g`.
  - [x] `acc_z_g`.
  - [x] `gyro_x_deg`.
  - [x] `gyro_y_deg`.
  - [x] `gyro_z_deg`.
- [x] Definisikan message `SensorBatch`:
  - [x] `session_id`.
  - [x] `device_id`.
  - [x] `start_seq`.
  - [x] `end_seq`.
  - [x] repeated `SensorSample`.
- [x] Buat `device_status.proto`.
- [x] Definisikan message `DeviceStatus`:
  - [x] `device_id`.
  - [x] `device_role`.
  - [x] `connected`.
  - [x] `recording`.
  - [x] `local_last_seq`.
  - [x] `backend_last_ack_seq`.
  - [x] `pending_samples`.
  - [x] `battery_percent`.
  - [x] `storage_free_mb`.
  - [x] `effective_hz`.
- [x] Buat `control.proto`.
- [x] Definisikan command backend ke phone:
  - [x] `START_SESSION`.
  - [x] `STOP_SESSION`.
  - [x] `SYNC_CLOCK`.
  - [x] `SYNC_REQUIRED`.
  - [x] `PING`.
- [ ] Generate Protobuf code untuk:
  - [x] Dart/Flutter.
  - [x] Python/FastAPI.
- [x] Tambahkan dokumentasi versi Protobuf:
  - [x] `schema_version`.
  - [x] backward compatibility policy.

### Phase 1 Notes

- Lokasi kontrak: `proto/`.
- Dokumen versi + policy ada di `proto/README.md`.
- Generate code sudah dijalankan:
  - Python output: `backend/generated/*_pb2.py`.
  - Dart output: `mobile-app/lib/generated/*.pb.dart`.

---

## Phase 2: Backend Foundation di Laptop

- [x] Buat project FastAPI.
- [x] Buat konfigurasi environment:
  - [x] host LAN.
  - [x] port REST API.
  - [x] port WebSocket.
  - [x] storage root SSD.
  - [x] webcam device index/path.
- [x] Buat app lifecycle:
  - [x] startup check.
  - [x] storage directory check.
  - [x] webcam availability check.
  - [x] graceful shutdown.
- [-] Buat session manager in-memory + persistent metadata.
- [x] Buat model metadata:
  - [x] `Device`.
  - [x] `Session`.
  - [x] `SessionDevice`.
  - [x] `Annotation`.
  - [x] `VideoRecording`.
  - [x] `PreflightCheck`.
  - [x] `FileArtifact`.
- [x] Pilih metadata storage:
  - [x] SQLite lokal untuk MVP.
  - [x] PostgreSQL/TimescaleDB jika nanti butuh query besar (sudah disiapkan via `DATABASE_URL`).
- [x] Buat REST endpoint device:
  - [x] `POST /devices/register`.
  - [x] `GET /devices`.
  - [x] `PATCH /devices/{device_id}`.
- [x] Buat REST endpoint session:
  - [x] `POST /sessions`.
  - [x] `POST /sessions/{session_id}/start`.
  - [x] `POST /sessions/{session_id}/stop`.
  - [x] `GET /sessions/{session_id}`.
  - [x] `GET /sessions/{session_id}/status`.
  - [x] `POST /sessions/{session_id}/finalize`.
- [x] Buat REST endpoint annotation:
  - [x] `POST /sessions/{session_id}/annotations/start`.
  - [x] `POST /sessions/{session_id}/annotations/{annotation_id}/stop`.
  - [x] `GET /sessions/{session_id}/annotations`.
  - [x] `PATCH /annotations/{annotation_id}`.
  - [x] `DELETE /annotations/{annotation_id}`.
- [x] Buat REST endpoint artifact:
  - [x] `GET /sessions/{session_id}/artifacts`.
  - [x] `GET /sessions/{session_id}/manifest.json`.
  - [x] `GET /sessions/{session_id}/export.zip`.
- [x] Buat endpoint health:
  - [x] `GET /health`.
  - [x] `GET /preflight`.

### Phase 2 Notes

- Root backend: `backend/`.
- Entry app: `backend/app/main.py`.
- Konfigurasi env: `backend/.env.example` + `backend/app/core/config.py`.
- Session manager: `backend/app/core/session_manager.py`.
- Metadata model: `backend/app/db/models.py`.
- Router endpoints: `backend/app/api/routers/`.
- Status parsial yang masih perlu penyelesaian:
  - session manager sudah enforce state machine, tapi belum ada recovery state lintas restart (akan diperdalam di fase berikutnya).

---

## Phase 3: Device WebSocket + ACK Protocol

- [x] Buat WebSocket untuk mobile nodes:
  ```text
  /ws/device/{device_id}
  ```
- [x] Buat WebSocket untuk dashboard:
  ```text
  /ws/dashboard/{session_id}
  ```
- [x] Implement device handshake:
  - [x] device kirim `HELLO`.
  - [x] backend validasi `device_id`.
  - [x] backend assign/konfirmasi `device_role`.
  - [x] backend kirim current session state.
- [x] Implement stream Protobuf dari phone:
  - [x] binary WebSocket frame untuk `SensorBatch`.
  - [x] fallback JSON hanya untuk debug.
- [x] Implement ACK dari backend:
  - [x] backend ack `last_received_seq`.
  - [x] backend ack per batch.
  - [x] duplicate batch tidak membuat data dobel.
- [x] Implement reconnect:
  - [x] phone kirim `local_last_seq`.
  - [x] backend balas `backend_last_seq`.
  - [x] phone upload missing batch dari seq berikutnya.
- [x] Implement timeout:
  - [x] device dianggap offline jika heartbeat hilang.
  - [x] dashboard menerima event device offline.
- [x] Implement dashboard forwarding:
  - [x] realtime sensor preview.
  - [x] status device.
  - [x] annotation events.
  - [x] video recorder status.
- [x] Tambahkan backpressure protection:
  - [x] limit batch size.
  - [x] drop hanya untuk realtime preview, bukan durable recording.
  - [x] warning kalau backend tidak sanggup menerima 100 Hz per device.

---

## Phase 4: Backend CSV Writer Per Device

- [x] Buat writer service untuk setiap `(session_id, device_id)`.
- [x] Saat session start, buat CSV file per device:
  ```text
  sessions/{session_id}/sensor/{device_role}_{device_id}.csv
  ```
- [x] Header CSV final:
  ```text
  session_id,device_id,device_role,seq,timestamp_device_unix_ns,timestamp_server_unix_ns,estimated_server_unix_ns,elapsed_ms,acc_x_g,acc_y_g,acc_z_g,gyro_x_deg,gyro_y_deg,gyro_z_deg
  ```
- [x] Writer harus append-only.
- [x] Writer harus flush berkala:
  - [x] flush per N sample.
  - [x] flush per N detik.
  - [x] flush saat stop session.
- [x] Tambahkan file lock/state supaya crash recovery bisa tahu CSV terakhir.
- [x] Tambahkan index/summary per device:
  - [x] first seq.
  - [x] last seq.
  - [x] sample count.
  - [x] missing seq ranges.
  - [x] effective Hz.
- [x] Pastikan duplicate sample tidak ditulis ulang:
  - [x] track last seq per device.
  - [x] skip duplicate seq.
  - [x] log gap jika seq lompat.
- [x] Tambahkan opsi raw binary archive:
  - [x] simpan Protobuf batch mentah untuk audit/debug.
  - [x] optional, bisa setelah MVP.

### Phase 4 Notes

- Service writer: `backend/app/services/csv_writer.py`.
- Integrasi lifecycle:
  - session start menyiapkan writer per device.
  - session stop melakukan flush + close writer + generate summary.
- Endpoint ingest MVP: `POST /sessions/{session_id}/ingest/sensor-batch` untuk menulis batch JSON ke CSV.

---

## Phase 5: Webcam Auto Recording

- [x] Pilih implementasi webcam recorder:
  - [x] OpenCV Python untuk MVP.
  - [x] FFmpeg subprocess jika butuh performa/stabilitas lebih baik.
- [x] Buat `VideoRecorderService`.
- [x] Deteksi webcam:
  - [x] camera index.
  - [x] resolution.
  - [x] fps.
  - [x] codec support.
- [x] Tambahkan preflight webcam:
  - [x] webcam connected.
  - [x] preview frame berhasil.
  - [x] fps mencukupi.
  - [x] storage cukup.
- [x] Saat `START_SESSION`:
  - [x] mulai video recording otomatis.
  - [x] catat `video_start_server_time`.
  - [x] catat `video_start_monotonic_ms`.
  - [x] simpan video ke SSD.
- [x] Saat `STOP_SESSION`:
  - [x] stop video recording otomatis.
  - [x] flush/close file video.
  - [x] catat `video_end_server_time`.
- [x] Format file video:
  ```text
  sessions/{session_id}/video/{session_id}_webcam.mp4
  ```
- [x] Tambahkan sidecar metadata:
  ```text
  sessions/{session_id}/video/{session_id}_webcam.json
  ```
- [x] Isi sidecar metadata video:
  - [x] `session_id`.
  - [x] `camera_id`.
  - [x] `fps`.
  - [x] `width`.
  - [x] `height`.
  - [x] `codec`.
  - [x] `video_start_server_time`.
  - [x] `video_end_server_time`.
  - [x] `duration_ms`.
  - [x] `frame_count`.
  - [x] `dropped_frame_estimate`.
- [x] Dashboard harus menampilkan:
  - [x] webcam connected/disconnected.
  - [x] video recording on/off.
  - [x] elapsed video time.
  - [x] video file path.
- [x] Tangani failure video:
  - [x] jika webcam tidak tersedia, session start diblokir kecuali operator override.
  - [x] jika video recorder gagal saat session berjalan, dashboard beri warning besar.
  - [x] session tetap bisa dilanjutkan atau dihentikan sesuai keputusan operator.

- [x] Integrasi deface untuk auto anonim muka di video anotasi

### Phase 5 Notes

- Recorder runtime ada di `backend/app/services/video_recorder.py`.
- API status untuk dashboard: `GET /sessions/{session_id}/video/status`.
- API sidecar metadata untuk dashboard:
  - `GET /sessions/{session_id}/video/metadata`
  - `GET /sessions/{session_id}/video/metadata/download`
- Preflight websocket tetap via `GET /preflight` dengan field webcam detail baru.

---

## Phase 6: Clock Sync dan Sinkronisasi Video-Sensor

- [x] Backend menjadi time authority untuk session.
- [x] Saat preflight, lakukan clock sync ke semua phone:
  - [x] ping/pong beberapa kali.
  - [x] hitung latency.
  - [x] hitung `clock_offset_ms`.
  - [x] simpan kualitas sync per device.
- [x] Saat start, backend broadcast:
  - [x] `session_id`.
  - [x] `server_start_time_unix_ns`.
  - [x] `recording_start_seq = 1`.
  - [x] target `sampling_hz = 100`.
- [ ] Phone menyimpan:
  - [ ] `device_start_time`.
  - [ ] `monotonic_start_ms`.
  - [ ] `server_start_time_unix_ns`.
- [x] Tiap sample menyertakan:
  - [x] `elapsed_ms`.
  - [x] `timestamp_device_unix_ns`.
- [x] Backend menghitung:
  ```text
  estimated_server_time = server_start_time + elapsed_ms
  ```
- [x] Video recorder memakai server monotonic time yang sama.
- [x] Simpan sync report:
  - [x] offset per device.
  - [x] latency min/median/max.
  - [x] sync quality.
  - [x] video start offset terhadap session start.
- [x] Dashboard tampilkan clock sync quality:
  - [x] green: good.
  - [x] yellow: warning.
  - [x] red: bad, start diblokir atau butuh override.

---

## Phase 7: Dashboard Browser

- [ ] Buat dashboard frontend dengan next-js pakai shadcdn-ui dan poppins font.
- [x] Buat layout utama:
  - [x] session header.
  - [x] elapsed timer.
  - [x] countdown barrier start realtime menuju `start_at_unix_ns`.
  - [x] device health cards.
  - [x] webcam status card.
  - [x] realtime graph area.
  - [x] annotation control.
  - [x] annotation list.
  - [x] preflight checklist.
  - [x] storage/artifact status.
- [x] Buat preflight checklist:
  - [x] backend healthy.
  - [x] storage path writable.
  - [x] storage free space cukup.
  - [x] webcam connected.
  - [x] webcam frame preview ok.
  - [x] semua required phone connected.
  - [x] tiap phone role sudah benar.
  - [x] tiap phone battery cukup.
  - [x] tiap phone storage cukup.
  - [x] clock sync quality ok.
  - [x] expected sampling rate 100 Hz.
- [x] Buat control session:
  - [x] create session.
  - [x] start session.
  - [x] stop session.
  - [x] finalize session.
  - [x] override preflight dengan alasan.
- [x] Buat annotation UI:
  - [x] pilih label.
  - [x] start annotation.
  - [x] stop annotation.
  - [x] auto-close annotation saat session stop.
  - [x] edit label/time/notes.
  - [x] delete annotation.
- [x] Buat annotation list:
  - [x] label.
  - [x] start time.
  - [x] end time.
  - [x] duration.
  - [x] status active/closed.
- [x] Buat realtime graphs:
  - [x] per role/device: chest, waist, thigh.
  - [x] accelerometer x/y/z.
  - [x] gyroscope x/y/z.
  - [x] rolling window 10-30 detik.
  - [x] tampilkan effective Hz.
- [x] Buat video panel:
  - [x] webcam preview sebelum record.
  - [x] recording indicator.
  - [x] elapsed video time.
  - [x] dropped frame warning jika tersedia.
  - [x] toggle `Anonymize video` (Yes/No), default `No` (tidak otomatis).
  - [x] tombol `Anonymize Now` untuk trigger manual proses anonymize.
  - [x] saat toggle `Yes`, saat stop/finalize tampilkan konfirmasi jalankan anonymize.
  - [x] panggil API `POST /sessions/{session_id}/video/anonymize` hanya jika toggle `Yes` atau tombol manual ditekan.
  - [x] tampilkan progress/status anonymize: pending/running/completed/failed.
  - [x] tampilkan path output anonymized video + metadata setelah selesai.
- [x] Buat artifact panel:
  - [x] CSV per device.
  - [x] video file.
  - [x] manifest file.
  - [x] export zip.
  - [x] upload-to-FAMS instructions/status.

---

## Phase 8: Flutter Mobile Node Refactor

- [ ] Tutup gap arsitektur mobile agar sesuai Wi-Fi WebSocket `100 Hz` (blocker MVP end-to-end):
  - [x] hentikan dependensi jalur utama Bluetooth parser untuk mode koleksi utama.
  - [x] buat connection manager ke endpoint `/ws/device/{device_id}`.
  - [x] dukung command control dari backend: `START_SESSION`, `STOP_SESSION`, `CLOCK_SYNC`.
  - [x] ubah sensor ticker default ke target sampling `100 Hz` stabil.
  - [x] simpan data lokal durable sebelum upload (SQLite/local queue).
  - [x] upload `SensorBatch` Protobuf via Wi-Fi dengan retry + resume.
  - [ ] verifikasi flow end-to-end phone sebagai IMU node Wi-Fi hingga backend ingest.

- [x] Update dependency Flutter:
  - [x] `web_socket_channel`.
  - [x] Protobuf runtime Dart.
  - [x] `sqflite`.
  - [x] `path_provider`.
  - [x] `uuid`.
  - [x] `battery_plus`.
  - [x] `connectivity_plus`.
- [x] Buat setup screen:
  - [x] backend URL/IP laptop.
  - [x] device name.
  - [x] device role: chest/waist/thigh/other.
  - [x] device ID persistent.
- [x] Buat connection manager:
  - [x] connect ke `/ws/device/{device_id}`.
  - [x] auto reconnect.
  - [x] heartbeat.
  - [x] receive backend command.
  - [x] ack handling.
- [x] Buat sensor sampler 100 Hz:
  - [x] sampling dari internal IMU.
  - [x] normalize accelerometer ke g.
  - [x] normalize gyro ke deg/s.
  - [x] emit fixed target rate 100 Hz.
- [x] Buat local durable storage:
  - [x] SQLite table `local_sessions`.
  - [x] SQLite table `sensor_samples`.
  - [x] SQLite table `upload_batches`.
- [x] Semua sample wajib ditulis lokal dulu:
  - [x] `session_id`.
  - [x] `device_id`.
  - [x] `device_role`.
  - [x] `seq`.
  - [x] `elapsed_ms`.
  - [x] raw sensor values.
  - [x] `uploaded = false`.
- [x] Implement Protobuf batch uploader:
  - [x] batch 250-1000 sample.
  - [x] kirim saat online.
  - [x] retry saat gagal.
  - [x] mark uploaded setelah ACK.
- [x] Implement session command:
  - [x] `START_SESSION` mulai local recording.
  - [x] `STOP_SESSION` stop local recording.
  - [x] `SYNC_REQUIRED` upload missing seq.
- [x] Implement offline mode:
  - [x] jika network putus, recording lokal tetap lanjut.
  - [x] setelah reconnect, upload backlog.
- [x] Implement crash recovery:
  - [x] detect unfinished local session.
  - [x] tampilkan recovered state.
  - [x] lanjut sync pending data.
- [ ] Buat mobile status UI:
  - [x] connected/offline.
  - [x] recording/not recording.
  - [x] current session.
  - [x] local sample count.
  - [x] pending upload.
  - [x] battery.
  - [x] storage free.
  - [x] effective Hz.

---

## Phase 9: Local Storage Layout di SSD

- [x] Buat root folder dataset:
  ```text
  DATA_ROOT/
    sessions/
  ```
- [x] Struktur session:
  ```text
  sessions/{session_id}/
    manifest.json
    session.json
    devices.json
    annotations.csv
    sync_report.json
    preflight_report.json
    sensor/
      chest_DEVICE-CHEST-001.csv
      waist_DEVICE-WAIST-001.csv
      thigh_DEVICE-THIGH-001.csv
    video/
      {session_id}_webcam.mp4
      {session_id}_webcam.json
    logs/
      backend.log
      device_events.log
      warnings.log
    export/
      {session_id}_dataset.zip
  ```
- [x] Backend membuat folder session saat session dibuat.
- [x] Backend menulis metadata session.
- [x] Backend menulis annotations CSV.
- [x] Backend menulis sync report.
- [x] Backend menulis preflight report.
- [x] Backend membuat export zip saat finalize.
- [x] Pastikan semua path aman:
  - [x] tidak ada karakter ilegal.
  - [x] tidak overwrite session lama.
  - [x] file partial diberi suffix `.partial`.
  - [x] rename atomik setelah file selesai.

---

## Phase 10: Failure Handling

- [x] Web dashboard refresh/close:
  - [x] recording tetap berjalan di backend.
  - [x] dashboard reconnect mengambil state terbaru.
  - [x] active annotation tetap muncul.
- [x] Backend restart:
  - [x] phone tetap menyimpan lokal.
  - [x] phone reconnect otomatis.
  - [x] backend recover session metadata dari disk.
  - [x] phone upload backlog.
- [x] Phone network putus:
  - [x] phone tetap record lokal.
  - [x] backend tandai offline.
  - [x] dashboard tampilkan last seen.
  - [x] sync ulang saat reconnect.
- [x] Phone app crash:
  - [x] data sebelum crash aman di SQLite.
  - [x] app recover unfinished session.
  - [x] upload pending data.
- [x] Phone baterai habis:
  - [x] backend tandai device lost.
  - [x] dataset bisa finalized incomplete jika operator setuju.
- [x] Storage laptop hampir penuh:
  - [x] preflight blok start.
  - [x] dashboard warning saat session berjalan.
  - [x] stop aman jika storage kritis.
- [x] Webcam gagal start:
  - [x] start session diblokir kecuali override.
  - [x] reason override disimpan.
- [x] Webcam gagal di tengah session:
  - [x] warning besar di dashboard.
  - [x] metadata video ditandai incomplete.
  - [x] session bisa dihentikan atau dilanjutkan sesuai operator.
- [x] Duplicate upload:
  - [x] backend skip duplicate seq.
  - [x] ACK tetap aman.
- [x] Missing sample:
  - [x] backend deteksi gap seq.
  - [x] gap masuk `sync_report.json`.
  - [x] dashboard tampilkan missing ranges.
- [x] Annotation lupa distop:
  - [x] auto-close saat session stop.
  - [x] tandai `auto_closed = true`.
- [x] Session stop saat device offline:
  - [x] session masuk `SYNCING`.
  - [x] tunggu device reconnect.
  - [x] operator bisa finalize incomplete.

---

## Phase 11: Session Finalization dan Export

- [x] Saat `STOP_SESSION`:
  - [x] broadcast stop ke semua phone online.
  - [x] stop webcam recorder.
  - [x] flush semua CSV writer.
  - [x] close annotation aktif.
  - [x] ubah status session ke `ENDING`.
- [x] Backend cek completeness:
  - [x] semua required device punya data.
  - [x] sample count masuk akal.
  - [x] tidak ada gap besar.
  - [x] video file valid.
  - [x] annotation lengkap.
- [x] Jika masih ada pending upload:
  - [x] status `SYNCING`.
  - [x] dashboard tampilkan device yang belum selesai.
- [x] Jika lengkap:
  - [x] status `COMPLETED`.
  - [x] buat manifest final.
  - [x] buat export zip.
- [x] Jika ada failure permanen:
  - [x] operator bisa `finalize incomplete`.
  - [x] wajib isi alasan.
  - [x] status `INCOMPLETE_FINALIZED`.
- [x] Export dataset harus berisi:
  - [x] CSV per device.
  - [x] video mp4.
  - [x] annotations.
  - [x] manifest.
  - [x] sync report.
  - [x] preflight report.
  - [x] failure/warning log.
- [x] Buat opsi export labeled dataset:
  - [x] join sample dengan annotation interval.
  - [x] output per device.
  - [x] output gabungan.
  - [x] include unlabeled sebagai empty/null.

---

## Phase 12: Manual Upload ke FAMS Server

- [x] Tetapkan FAMS server target:
  - [x] host.
  - [x] user.
  - [x] destination path.
  - [x] SSH key.
- [x] Buat script manual upload:
  ```text
  scripts/upload_to_fams.ps1
  scripts/upload_to_fams.sh
  ```
- [x] Script upload memakai:
  - [x] `rsync`.
  - [x] checksum sebelum/sesudah upload.
  - [x] resume jika upload gagal, jika memakai `rsync`.
- [x] Dashboard tampilkan instruksi upload:
  - [x] path export zip.
  - [x] command upload.
  - [x] checksum file.
- [x] Simpan upload metadata:
  - [x] uploaded/not uploaded.
  - [x] uploaded_at.
  - [x] uploaded_by.
  - [x] remote_path.
  - [x] checksum.
- [x] Tambahkan manual confirmation:
  - [x] operator klik `Mark as uploaded`.
  - [x] backend simpan status archive.

---

## Phase 13: Monitoring, Simulator, dan QA

- [x] Buat simulator device untuk test tanpa 3 HP:
  - [x] simulate chest.
  - [x] simulate waist.
  - [x] simulate thigh.
  - [x] emit Protobuf 100 Hz.
  - [x] simulate disconnect/reconnect.
- [x] Buat webcam test mode:
  - [x] record 10 detik.
  - [x] validate output mp4.
  - [x] hitung frame count.
- [x] Tambahkan backend metrics:
  - [x] samples/sec per device.
  - [x] effective Hz.
  - [x] dropped/gap samples.
  - [x] websocket reconnect count.
  - [x] upload retry count.
  - [x] CSV write latency.
  - [x] video fps.
  - [x] storage free.
- [x] Tambahkan test backend:
  - [x] Protobuf decode.
  - [x] batch ACK.
  - [x] duplicate seq.
  - [x] missing seq detection.
  - [x] annotation start/stop.
  - [x] session state machine.
  - [x] video recorder start/stop mocked.
- [x] Tambahkan test Flutter:
  - [x] local SQLite persistence.
  - [x] seq monotonic.
  - [x] reconnect upload.
  - [x] command handling.
- Catatan: prosedur uji lapangan terdokumentasi di `scripts/phase13_field_runbook.md`.
- [ ] Uji skenario lapangan:
  - [ ] start dengan 3 phone online.
  - [ ] matikan Wi-Fi salah satu phone saat recording.
  - [ ] nyalakan lagi dan pastikan backlog sync.
  - [ ] refresh dashboard saat annotation aktif.
  - [ ] restart backend saat recording.
  - [ ] cabut webcam sebelum start.
  - [ ] cabut webcam saat recording.
  - [ ] storage laptop hampir penuh.
  - [ ] session end saat phone offline.
  - [ ] upload manual ke FAMS.

---

## Phase 14: Deployment LAN Laptop

- [ ] Buat Docker Compose untuk laptop:
  - [ ] backend.
  - [ ] frontend.
  - [ ] optional database.
- [ ] Pastikan webcam access bisa berjalan:
  - [ ] native backend lebih mudah untuk webcam.
  - [ ] Docker webcam butuh mapping device khusus, evaluasi dulu.
- [ ] Buat `.env.example`:
  - [ ] `BACKEND_HOST`.
  - [ ] `BACKEND_PORT`.
  - [ ] `DASHBOARD_PORT`.
  - [ ] `DATA_ROOT`.
  - [ ] `WEBCAM_INDEX`.
  - [ ] `FAMS_HOST`.
  - [ ] `FAMS_USER`.
  - [ ] `FAMS_REMOTE_PATH`.
- [ ] Buat startup script:
  - [ ] `scripts/start_backend.ps1`.
  - [ ] `scripts/start_dashboard.ps1`.
  - [ ] `scripts/start_all.ps1`.
- [ ] Buat dokumentasi operator:
  - [ ] cara connect phone ke Wi-Fi LAN.
  - [ ] cara set backend IP di phone.
  - [ ] cara preflight.
  - [ ] cara start/stop session.
  - [ ] cara membuat annotation.
  - [ ] cara verify video.
  - [ ] cara export.
  - [ ] cara upload ke FAMS.
  - [ ] cara recovery jika device gagal.

---

## Urutan Implementasi Paling Disarankan

1. Buat Protobuf schema sensor/status/control.
2. Buat FastAPI WebSocket device receiver.
3. Buat simulator 3 device yang emit Protobuf 100 Hz.
4. Buat CSV writer per device di SSD.
5. Buat dashboard minimal untuk status device dan start/stop session.
6. Tambahkan annotation start/stop dan annotation list.
7. Tambahkan webcam auto recording saat session start/stop.
8. Tambahkan preflight checklist.
9. Refactor Flutter app supaya connect ke backend dan kirim Protobuf.
10. Tambahkan local SQLite buffer di Flutter.
11. Tambahkan reconnect sync dan ACK protocol.
12. Tambahkan finalization, manifest, export zip.
13. Tambahkan manual SSH upload workflow ke FAMS.
14. Uji semua failure scenario.

---

## MVP Definition

MVP dianggap berhasil jika alur ini jalan:

```text
3 Android phones connect ke laptop LAN
-> dashboard preflight pass
-> operator klik Start
-> backend broadcast START ke phones
-> phones kirim Protobuf IMU 100 Hz
-> backend tulis CSV per device
-> webcam otomatis mulai record
-> dashboard menampilkan graph realtime dan timer
-> operator start/stop annotation
-> operator klik Stop
-> backend stop phones dan webcam
-> backend flush CSV + save video + manifest
-> session finalized
-> export zip siap diupload manual ke FAMS
```

---

## Reliability Definition

Sistem dianggap tahan failure jika:

```text
phone offline -> phone tetap record lokal -> reconnect -> backlog sync
web refresh -> session tetap berjalan -> dashboard recover state
backend restart -> phone reconnect -> pending samples dikirim ulang
duplicate upload -> backend tidak menulis data dobel
webcam gagal -> dashboard memberi warning dan metadata mencatat failure
session incomplete -> operator bisa finalize incomplete dengan alasan
```

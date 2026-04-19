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
- [-] Buat app lifecycle:
  - [x] startup check.
  - [x] storage directory check.
  - [x] webcam availability check.
  - [ ] graceful shutdown.
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
- [-] Buat REST endpoint artifact:
  - [x] `GET /sessions/{session_id}/artifacts`.
  - [-] `GET /sessions/{session_id}/manifest.json`.
  - [-] `GET /sessions/{session_id}/export.zip`.
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
  - graceful shutdown masih placeholder hook.
  - artifact `manifest.json` dan `export.zip` belum otomatis diproduksi oleh worker finalization.
  - session manager sudah enforce state machine, tapi belum ada recovery state lintas restart (akan diperdalam di fase berikutnya).

---

## Phase 3: Device WebSocket + ACK Protocol

- [ ] Buat WebSocket untuk mobile nodes:
  ```text
  /ws/device/{device_id}
  ```
- [ ] Buat WebSocket untuk dashboard:
  ```text
  /ws/dashboard/{session_id}
  ```
- [ ] Implement device handshake:
  - [ ] device kirim `HELLO`.
  - [ ] backend validasi `device_id`.
  - [ ] backend assign/konfirmasi `device_role`.
  - [ ] backend kirim current session state.
- [ ] Implement stream Protobuf dari phone:
  - [ ] binary WebSocket frame untuk `SensorBatch`.
  - [ ] fallback JSON hanya untuk debug.
- [ ] Implement ACK dari backend:
  - [ ] backend ack `last_received_seq`.
  - [ ] backend ack per batch.
  - [ ] duplicate batch tidak membuat data dobel.
- [ ] Implement reconnect:
  - [ ] phone kirim `local_last_seq`.
  - [ ] backend balas `backend_last_seq`.
  - [ ] phone upload missing batch dari seq berikutnya.
- [ ] Implement timeout:
  - [ ] device dianggap offline jika heartbeat hilang.
  - [ ] dashboard menerima event device offline.
- [ ] Implement dashboard forwarding:
  - [ ] realtime sensor preview.
  - [ ] status device.
  - [ ] annotation events.
  - [ ] video recorder status.
- [ ] Tambahkan backpressure protection:
  - [ ] limit batch size.
  - [ ] drop hanya untuk realtime preview, bukan durable recording.
  - [ ] warning kalau backend tidak sanggup menerima 100 Hz per device.

---

## Phase 4: Backend CSV Writer Per Device

- [ ] Buat writer service untuk setiap `(session_id, device_id)`.
- [ ] Saat session start, buat CSV file per device:
  ```text
  sessions/{session_id}/sensor/{device_role}_{device_id}.csv
  ```
- [ ] Header CSV final:
  ```text
  session_id,device_id,device_role,seq,timestamp_device_unix_ns,timestamp_server_unix_ns,estimated_server_unix_ns,elapsed_ms,acc_x_g,acc_y_g,acc_z_g,gyro_x_deg,gyro_y_deg,gyro_z_deg
  ```
- [ ] Writer harus append-only.
- [ ] Writer harus flush berkala:
  - [ ] flush per N sample.
  - [ ] flush per N detik.
  - [ ] flush saat stop session.
- [ ] Tambahkan file lock/state supaya crash recovery bisa tahu CSV terakhir.
- [ ] Tambahkan index/summary per device:
  - [ ] first seq.
  - [ ] last seq.
  - [ ] sample count.
  - [ ] missing seq ranges.
  - [ ] effective Hz.
- [ ] Pastikan duplicate sample tidak ditulis ulang:
  - [ ] track last seq per device.
  - [ ] skip duplicate seq.
  - [ ] log gap jika seq lompat.
- [ ] Tambahkan opsi raw binary archive:
  - [ ] simpan Protobuf batch mentah untuk audit/debug.
  - [ ] optional, bisa setelah MVP.

---

## Phase 5: Webcam Auto Recording

- [ ] Pilih implementasi webcam recorder:
  - [ ] OpenCV Python untuk MVP.
  - [ ] FFmpeg subprocess jika butuh performa/stabilitas lebih baik.
- [ ] Buat `VideoRecorderService`.
- [ ] Deteksi webcam:
  - [ ] camera index.
  - [ ] resolution.
  - [ ] fps.
  - [ ] codec support.
- [ ] Tambahkan preflight webcam:
  - [ ] webcam connected.
  - [ ] preview frame berhasil.
  - [ ] fps mencukupi.
  - [ ] storage cukup.
- [ ] Saat `START_SESSION`:
  - [ ] mulai video recording otomatis.
  - [ ] catat `video_start_server_time`.
  - [ ] catat `video_start_monotonic_ms`.
  - [ ] simpan video ke SSD.
- [ ] Saat `STOP_SESSION`:
  - [ ] stop video recording otomatis.
  - [ ] flush/close file video.
  - [ ] catat `video_end_server_time`.
- [ ] Format file video:
  ```text
  sessions/{session_id}/video/{session_id}_webcam.mp4
  ```
- [ ] Tambahkan sidecar metadata:
  ```text
  sessions/{session_id}/video/{session_id}_webcam.json
  ```
- [ ] Isi sidecar metadata video:
  - [ ] `session_id`.
  - [ ] `camera_id`.
  - [ ] `fps`.
  - [ ] `width`.
  - [ ] `height`.
  - [ ] `codec`.
  - [ ] `video_start_server_time`.
  - [ ] `video_end_server_time`.
  - [ ] `duration_ms`.
  - [ ] `frame_count`.
  - [ ] `dropped_frame_estimate`.
- [ ] Dashboard harus menampilkan:
  - [ ] webcam connected/disconnected.
  - [ ] video recording on/off.
  - [ ] elapsed video time.
  - [ ] video file path.
- [ ] Tangani failure video:
  - [ ] jika webcam tidak tersedia, session start diblokir kecuali operator override.
  - [ ] jika video recorder gagal saat session berjalan, dashboard beri warning besar.
  - [ ] session tetap bisa dilanjutkan atau dihentikan sesuai keputusan operator.

---

## Phase 6: Clock Sync dan Sinkronisasi Video-Sensor

- [ ] Backend menjadi time authority untuk session.
- [ ] Saat preflight, lakukan clock sync ke semua phone:
  - [ ] ping/pong beberapa kali.
  - [ ] hitung latency.
  - [ ] hitung `clock_offset_ms`.
  - [ ] simpan kualitas sync per device.
- [ ] Saat start, backend broadcast:
  - [ ] `session_id`.
  - [ ] `server_start_time_unix_ns`.
  - [ ] `recording_start_seq = 1`.
  - [ ] target `sampling_hz = 100`.
- [ ] Phone menyimpan:
  - [ ] `device_start_time`.
  - [ ] `monotonic_start_ms`.
  - [ ] `server_start_time_unix_ns`.
- [ ] Tiap sample menyertakan:
  - [ ] `elapsed_ms`.
  - [ ] `timestamp_device_unix_ns`.
- [ ] Backend menghitung:
  ```text
  estimated_server_time = server_start_time + elapsed_ms
  ```
- [ ] Video recorder memakai server monotonic time yang sama.
- [ ] Simpan sync report:
  - [ ] offset per device.
  - [ ] latency min/median/max.
  - [ ] sync quality.
  - [ ] video start offset terhadap session start.
- [ ] Dashboard tampilkan clock sync quality:
  - [ ] green: good.
  - [ ] yellow: warning.
  - [ ] red: bad, start diblokir atau butuh override.

---

## Phase 7: Dashboard Browser

- [ ] Buat dashboard frontend dengan next-js.
- [ ] Buat layout utama:
  - [ ] session header.
  - [ ] elapsed timer.
  - [ ] device health cards.
  - [ ] webcam status card.
  - [ ] realtime graph area.
  - [ ] annotation control.
  - [ ] annotation list.
  - [ ] preflight checklist.
  - [ ] storage/artifact status.
- [ ] Buat preflight checklist:
  - [ ] backend healthy.
  - [ ] storage path writable.
  - [ ] storage free space cukup.
  - [ ] webcam connected.
  - [ ] webcam frame preview ok.
  - [ ] semua required phone connected.
  - [ ] tiap phone role sudah benar.
  - [ ] tiap phone battery cukup.
  - [ ] tiap phone storage cukup.
  - [ ] clock sync quality ok.
  - [ ] expected sampling rate 100 Hz.
- [ ] Buat control session:
  - [ ] create session.
  - [ ] start session.
  - [ ] stop session.
  - [ ] finalize session.
  - [ ] override preflight dengan alasan.
- [ ] Buat annotation UI:
  - [ ] pilih label.
  - [ ] start annotation.
  - [ ] stop annotation.
  - [ ] auto-close annotation saat session stop.
  - [ ] edit label/time/notes.
  - [ ] delete annotation.
- [ ] Buat annotation list:
  - [ ] label.
  - [ ] start time.
  - [ ] end time.
  - [ ] duration.
  - [ ] status active/closed.
- [ ] Buat realtime graphs:
  - [ ] per role/device: chest, waist, thigh.
  - [ ] accelerometer x/y/z.
  - [ ] gyroscope x/y/z.
  - [ ] rolling window 10-30 detik.
  - [ ] tampilkan effective Hz.
- [ ] Buat video panel:
  - [ ] webcam preview sebelum record.
  - [ ] recording indicator.
  - [ ] elapsed video time.
  - [ ] dropped frame warning jika tersedia.
- [ ] Buat artifact panel:
  - [ ] CSV per device.
  - [ ] video file.
  - [ ] manifest file.
  - [ ] export zip.
  - [ ] upload-to-FAMS instructions/status.

---

## Phase 8: Flutter Mobile Node Refactor

- [ ] Update dependency Flutter:
  - [ ] `web_socket_channel`.
  - [ ] Protobuf runtime Dart.
  - [ ] `sqflite`.
  - [ ] `path_provider`.
  - [ ] `uuid`.
  - [ ] `battery_plus`.
  - [ ] `connectivity_plus`.
- [ ] Buat setup screen:
  - [ ] backend URL/IP laptop.
  - [ ] device name.
  - [ ] device role: chest/waist/thigh/other.
  - [ ] device ID persistent.
- [ ] Buat connection manager:
  - [ ] connect ke `/ws/device/{device_id}`.
  - [ ] auto reconnect.
  - [ ] heartbeat.
  - [ ] receive backend command.
  - [ ] ack handling.
- [ ] Buat sensor sampler 100 Hz:
  - [ ] sampling dari internal IMU.
  - [ ] normalize accelerometer ke g.
  - [ ] normalize gyro ke deg/s.
  - [ ] emit fixed target rate 100 Hz.
- [ ] Buat local durable storage:
  - [ ] SQLite table `local_sessions`.
  - [ ] SQLite table `sensor_samples`.
  - [ ] SQLite table `upload_batches`.
- [ ] Semua sample wajib ditulis lokal dulu:
  - [ ] `session_id`.
  - [ ] `device_id`.
  - [ ] `device_role`.
  - [ ] `seq`.
  - [ ] `elapsed_ms`.
  - [ ] raw sensor values.
  - [ ] `uploaded = false`.
- [ ] Implement Protobuf batch uploader:
  - [ ] batch 250-1000 sample.
  - [ ] kirim saat online.
  - [ ] retry saat gagal.
  - [ ] mark uploaded setelah ACK.
- [ ] Implement session command:
  - [ ] `START_SESSION` mulai local recording.
  - [ ] `STOP_SESSION` stop local recording.
  - [ ] `SYNC_REQUIRED` upload missing seq.
- [ ] Implement offline mode:
  - [ ] jika network putus, recording lokal tetap lanjut.
  - [ ] setelah reconnect, upload backlog.
- [ ] Implement crash recovery:
  - [ ] detect unfinished local session.
  - [ ] tampilkan recovered state.
  - [ ] lanjut sync pending data.
- [ ] Buat mobile status UI:
  - [ ] connected/offline.
  - [ ] recording/not recording.
  - [ ] current session.
  - [ ] local sample count.
  - [ ] pending upload.
  - [ ] battery.
  - [ ] storage free.
  - [ ] effective Hz.

---

## Phase 9: Local Storage Layout di SSD

- [ ] Buat root folder dataset:
  ```text
  DATA_ROOT/
    sessions/
  ```
- [ ] Struktur session:
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
- [ ] Backend membuat folder session saat session dibuat.
- [ ] Backend menulis metadata session.
- [ ] Backend menulis annotations CSV.
- [ ] Backend menulis sync report.
- [ ] Backend menulis preflight report.
- [ ] Backend membuat export zip saat finalize.
- [ ] Pastikan semua path aman:
  - [ ] tidak ada karakter ilegal.
  - [ ] tidak overwrite session lama.
  - [ ] file partial diberi suffix `.partial`.
  - [ ] rename atomik setelah file selesai.

---

## Phase 10: Failure Handling

- [ ] Web dashboard refresh/close:
  - [ ] recording tetap berjalan di backend.
  - [ ] dashboard reconnect mengambil state terbaru.
  - [ ] active annotation tetap muncul.
- [ ] Backend restart:
  - [ ] phone tetap menyimpan lokal.
  - [ ] phone reconnect otomatis.
  - [ ] backend recover session metadata dari disk.
  - [ ] phone upload backlog.
- [ ] Phone network putus:
  - [ ] phone tetap record lokal.
  - [ ] backend tandai offline.
  - [ ] dashboard tampilkan last seen.
  - [ ] sync ulang saat reconnect.
- [ ] Phone app crash:
  - [ ] data sebelum crash aman di SQLite.
  - [ ] app recover unfinished session.
  - [ ] upload pending data.
- [ ] Phone baterai habis:
  - [ ] backend tandai device lost.
  - [ ] dataset bisa finalized incomplete jika operator setuju.
- [ ] Storage laptop hampir penuh:
  - [ ] preflight blok start.
  - [ ] dashboard warning saat session berjalan.
  - [ ] stop aman jika storage kritis.
- [ ] Webcam gagal start:
  - [ ] start session diblokir kecuali override.
  - [ ] reason override disimpan.
- [ ] Webcam gagal di tengah session:
  - [ ] warning besar di dashboard.
  - [ ] metadata video ditandai incomplete.
  - [ ] session bisa dihentikan atau dilanjutkan sesuai operator.
- [ ] Duplicate upload:
  - [ ] backend skip duplicate seq.
  - [ ] ACK tetap aman.
- [ ] Missing sample:
  - [ ] backend deteksi gap seq.
  - [ ] gap masuk `sync_report.json`.
  - [ ] dashboard tampilkan missing ranges.
- [ ] Annotation lupa distop:
  - [ ] auto-close saat session stop.
  - [ ] tandai `auto_closed = true`.
- [ ] Session stop saat device offline:
  - [ ] session masuk `SYNCING`.
  - [ ] tunggu device reconnect.
  - [ ] operator bisa finalize incomplete.

---

## Phase 11: Session Finalization dan Export

- [ ] Saat `STOP_SESSION`:
  - [ ] broadcast stop ke semua phone online.
  - [ ] stop webcam recorder.
  - [ ] flush semua CSV writer.
  - [ ] close annotation aktif.
  - [ ] ubah status session ke `ENDING`.
- [ ] Backend cek completeness:
  - [ ] semua required device punya data.
  - [ ] sample count masuk akal.
  - [ ] tidak ada gap besar.
  - [ ] video file valid.
  - [ ] annotation lengkap.
- [ ] Jika masih ada pending upload:
  - [ ] status `SYNCING`.
  - [ ] dashboard tampilkan device yang belum selesai.
- [ ] Jika lengkap:
  - [ ] status `COMPLETED`.
  - [ ] buat manifest final.
  - [ ] buat export zip.
- [ ] Jika ada failure permanen:
  - [ ] operator bisa `finalize incomplete`.
  - [ ] wajib isi alasan.
  - [ ] status `INCOMPLETE_FINALIZED`.
- [ ] Export dataset harus berisi:
  - [ ] CSV per device.
  - [ ] video mp4.
  - [ ] annotations.
  - [ ] manifest.
  - [ ] sync report.
  - [ ] preflight report.
  - [ ] failure/warning log.
- [ ] Buat opsi export labeled dataset:
  - [ ] join sample dengan annotation interval.
  - [ ] output per device.
  - [ ] output gabungan.
  - [ ] include unlabeled sebagai empty/null.

---

## Phase 12: Manual Upload ke FAMS Server

- [ ] Tetapkan FAMS server target:
  - [ ] host.
  - [ ] user.
  - [ ] destination path.
  - [ ] SSH key.
- [ ] Buat script manual upload:
  ```text
  scripts/upload_to_fams.ps1
  scripts/upload_to_fams.sh
  ```
- [ ] Script upload memakai:
  - [ ] `scp` atau `rsync`.
  - [ ] checksum sebelum/sesudah upload.
  - [ ] resume jika upload gagal, jika memakai `rsync`.
- [ ] Dashboard tampilkan instruksi upload:
  - [ ] path export zip.
  - [ ] command upload.
  - [ ] checksum file.
- [ ] Simpan upload metadata:
  - [ ] uploaded/not uploaded.
  - [ ] uploaded_at.
  - [ ] uploaded_by.
  - [ ] remote_path.
  - [ ] checksum.
- [ ] Tambahkan manual confirmation:
  - [ ] operator klik `Mark as uploaded`.
  - [ ] backend simpan status archive.

---

## Phase 13: Monitoring, Simulator, dan QA

- [ ] Buat simulator device untuk test tanpa 3 HP:
  - [ ] simulate chest.
  - [ ] simulate waist.
  - [ ] simulate thigh.
  - [ ] emit Protobuf 100 Hz.
  - [ ] simulate disconnect/reconnect.
- [ ] Buat webcam test mode:
  - [ ] record 10 detik.
  - [ ] validate output mp4.
  - [ ] hitung frame count.
- [ ] Tambahkan backend metrics:
  - [ ] samples/sec per device.
  - [ ] effective Hz.
  - [ ] dropped/gap samples.
  - [ ] websocket reconnect count.
  - [ ] upload retry count.
  - [ ] CSV write latency.
  - [ ] video fps.
  - [ ] storage free.
- [ ] Tambahkan test backend:
  - [ ] Protobuf decode.
  - [ ] batch ACK.
  - [ ] duplicate seq.
  - [ ] missing seq detection.
  - [ ] annotation start/stop.
  - [ ] session state machine.
  - [ ] video recorder start/stop mocked.
- [ ] Tambahkan test Flutter:
  - [ ] local SQLite persistence.
  - [ ] seq monotonic.
  - [ ] reconnect upload.
  - [ ] command handling.
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

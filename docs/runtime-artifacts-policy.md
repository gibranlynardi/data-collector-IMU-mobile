# Runtime Artifacts Policy

Tujuan: mencegah artefak runtime biner (DB/backup) masuk version control.

## Jangan commit artefak runtime

- `data/`
- `backend/data/`
- `backups/`
- `*.db`
- `*.zip`

Semua item di atas sudah di-ignore di `.gitignore` root.

## Simpan contoh schema dalam file teks

Jika butuh contoh schema SQLite, simpan sebagai file `.sql` teks di folder `docs/`.

Contoh command untuk generate schema dari DB lokal:

```powershell
sqlite3 data/metadata.db ".schema" > docs/metadata_schema_example.sql
```

Jangan commit file DB biner hasil runtime.

## Simpan contoh environment dalam file teks

Gunakan:

- `.env.example`
- `backend/.env.example`

Jangan commit file `.env` berisi kredensial nyata.

## IMU Collector Web Dashboard (Phase 7)

Dashboard browser untuk operasi session IMU multi-device via backend FastAPI.

Fitur utama yang sudah diimplementasikan:

- Session header + elapsed timer + status.
- Countdown barrier realtime menuju `start_at_unix_ns`.
- Session controls: create/start/stop/finalize.
- Preflight checklist (backend, storage, webcam, device readiness, sync quality).
- Device health cards.
- Annotation controls + list (start/stop/edit/delete).
- Realtime graph area berbasis event `SENSOR_PREVIEW` dari WebSocket dashboard.
- Video panel + trigger `Anonymize Now`.
- Artifact panel dari endpoint backend.

## Setup

Copy env berikut bila perlu (opsional):

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8000
```

Default sudah mengarah ke `127.0.0.1:8000`.

## Run

Jalankan dashboard:

```bash
npm run dev
```

Lalu buka `http://localhost:3000`.

## Build Check

```bash
npm run lint
npm run build
```

## Notes

- UI menggunakan Next.js App Router + Tailwind CSS.
- Typography: Poppins + Sora.
- Integrasi data kombinasi polling REST + streaming WS dashboard.
- JSON fallback tetap diterima backend untuk kompatibilitas event existing.

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

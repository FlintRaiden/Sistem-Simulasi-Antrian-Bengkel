# Simulasi Antrian Bengkel (Discrete-Event Simulation)

Aplikasi web Flask untuk mensimulasikan antrian bengkel dengan DES murni (tanpa SimPy).
Sistem: **1 resepsionis/kasir** dan **2 montir**. Disiplin antrian: **FIFO, LIFO, RANDOM**.

Alur: `Colab (.ipynb)` → `models/bengkel_des_model.joblib` → `Flask (api/index.py)` → Vercel.

## Struktur
```
notebooks/simulasi_bengkel_colab.ipynb   # rancang, uji, ekspor .joblib
models/bengkel_des_model.joblib          # hasil ekspor (di-commit ke GitHub)
simulation/engine.py                     # engine DES (dipakai Colab dan Flask)
api/index.py                             # Flask + joblib.load (entry point Vercel)
templates/index.html, static/            # antarmuka web
vercel.json, requirements.txt
```

## 1. Generate file .joblib di Google Colab
1. Buka `notebooks/simulasi_bengkel_colab.ipynb` di [Google Colab](https://colab.research.google.com) (File → Upload notebook).
2. Jalankan semua sel (Runtime → Run all). Sel pertama menulis `simulation/engine.py`, sel terakhir menjalankan `joblib.dump(...)` ke `models/bengkel_des_model.joblib` lalu mengunduhnya.
3. Salin file hasil unduhan ke folder `models/` di repo, lalu commit.
   (Repo ini sudah menyertakan file `.joblib` contoh dengan parameter default.)

Nilai default form mode acak di web diambil dari parameter yang disimpan di `.joblib`.
Jika file tidak ada atau gagal dimuat, backend otomatis memakai class di `simulation/engine.py`
(badge di header web menampilkan sumber engine yang aktif).

## 2. Jalankan lokal
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python api/index.py
```
Buka http://127.0.0.1:5000

## 3. Deploy ke Vercel
1. Push seluruh folder ke GitHub (pastikan `models/bengkel_des_model.joblib` ikut ter-commit).
2. Di [vercel.com](https://vercel.com) pilih **Add New → Project**, import repo, lalu **Deploy** (tanpa pengaturan tambahan).
   Atau lewat CLI: `npm i -g vercel && vercel --prod`.
3. `vercel.json` mengarahkan semua route ke `api/index.py` dan menyertakan `templates/`, `static/`, `models/`, `simulation/` ke dalam bundle function.

> Gunakan versi library yang sama saat membuat `.joblib` (di Colab) dan saat deploy. Pickle bisa gagal dimuat jika versi berbeda jauh; jika itu terjadi, aplikasi tetap jalan lewat fallback.

## Aturan model
- Event: `ARRIVAL`, `REGISTRATION`, `SERVICE_CHECK`, `SERVICE_START`, `SERVICE_END`, `PAYMENT`, `DEPARTURE`.
- Montir 1 diutamakan jika kedua montir `IDLE`.
- Jika resepsionis bebas dan antrian pendaftaran serta antrian kasir sama-sama terisi, **kasir didahulukan**.
- Disiplin antrian berlaku di ketiga antrian (resepsionis, ruang tunggu bengkel, kasir).
- Event pada Clock yang sama diproses dengan urutan: `PAY_END`, `SERVICE_END`, `REG_END`, `ARRIVAL`.
- Mode acak: antar-kedatangan eksponensial; durasi layanan normal (minimum 0,5 menit). Mobil pertama datang pada Clock 0.
- Mode manual: satu angka pada waktu pendaftaran/pembayaran berlaku untuk semua mobil.
- Waktu tunggu pada kartu statistik = waktu di ruang tunggu bengkel (sebelum masuk montir); waktu tunggu resepsionis/kasir tersedia di kolom log.

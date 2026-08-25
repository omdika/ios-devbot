# Telegram AI Fullstack Coding Agent

AI Agent berbasis Telegram Bot yang terhubung ke **Google Cloud Vertex AI (Gemini)** untuk otomatisasi pengembangan Backend Python dan iOS Swift/SwiftUI langsung ke GitHub via Pull Request.

---

## 🔄 Alur Kerja Bot (Bot Flow)

Bot bekerja dengan alur terstruktur dari penerimaan instruksi hingga penggabungan kode (merge):

```
[User Telegram] 
       │ 
       ├─► Kirim Pesan / Screenshot Gambar
       │
[Debouncer (2.5 detik)] ──► Menggabungkan pesan beruntun (multiline & multi-image)
       │
[execute_task (Lock per User)] ──► Mencegah konflik proses bersamaan
       │
[Workspace Sync] ──► Clone / Checkout branch baru (`ai-task-<msg_id>`)
       │
[Codebase Scan & Cache] ──► Scan file backend & iOS (disimpan di memori sesi)
       │
[Vertex AI (gemini-2.5-flash)] ──► Mengirim prompt + codebase snapshot + screenshot
       │
[Streaming Telegram Status] ──► Update log respon AI secara real-time ke user
       │
[Code Parser & Write] ──► Menulis file kode baru/edit ke workspace lokal
       │
[Git Push & PR Creation] ──► Commit perubahan, push branch, & buat Pull Request di GitHub
       │
[User Action in Telegram] ──► Mengklik tombol "Merge Backend" / "Merge iOS"
       │
[PR Auto-Merge & Reset] ──► Merge PR di GitHub & hapus cache codebase sesi
```

### Detail Langkah Flow:
1. **Debouncing & Penanganan Media**: Saat Anda mengirim chat teks dengan satu atau beberapa gambar secara terpisah, bot akan menunggu selama **2.5 detik** sebelum memprosesnya untuk memastikan seluruh media/teks tergabung dalam satu instruksi (`handle_incoming`).
2. **Kunci Sesi & Sinkronisasi Repo**: Bot mengunci proses untuk user tersebut agar tidak terjadi konflik data. Bot melakukan sinkronisasi repositori backend/iOS (clone/pull dari branch `main`), lalu membuat branch baru khusus untuk task tersebut: `ai-task-<telegram_message_id>`.
3. **Penyimpanan Snapshot Codebase (Caching)**:
   - Pada request pertama, bot melakukan pemindaian lengkap terhadap codebase proyek backend dan iOS yang relevan (`scan_repo_files`) di thread terpisah agar bot tidak mengalami *freeze* (memakai `run_in_executor`).
   - Snapshot ini disimpan dalam cache memori sesi aktif. Pada perintah berikutnya, bot akan menggunakan cache memori ini sehingga pemrosesan Vertex AI menjadi jauh lebih cepat dan menghemat resource.
4. **Respon Streaming & Penulisan Kode**: Bot mengirimkan instruksi beserta snapshot kode ke **Vertex AI GCP (`gemini-2.5-flash`)**. Output dari Vertex AI dikirim secara *streaming* ke Telegram agar user dapat memantau penulisan kode secara langsung. Kode yang dihasilkan kemudian di-parsing dan ditulis langsung ke disk lokal workspace (`workspace/backend` atau `workspace/ios`).
5. **Pembuatan Pull Request & Penggabungan (Merge)**: Jika ada perubahan kode terdeteksi, bot akan melakukan `git commit` dan `git push` ke branch tugas, lalu membuat Pull Request (PR) di GitHub secara otomatis. Bot mengirimkan tombol inline di Telegram. Ketika Anda mengklik tombol **Merge**, bot akan menggabungkan PR tersebut ke branch `main` di GitHub dan otomatis membersihkan cache codebase di Telegram agar perubahan terbaru dibaca pada tugas berikutnya.

---

## 🛠️ Persyaratan & Cara Setup (Requirements Setup)

### 1. Setup Telegram Bot & User ID
1. Buka aplikasi Telegram Anda, cari bot **@BotFather**.
2. Kirim perintah `/newbot` dan ikuti instruksinya untuk menentukan nama bot dan username.
3. Setelah selesai, Anda akan mendapatkan **Telegram Bot Token** (simpan token ini untuk `.env`).
4. Untuk keamanan, bot ini hanya dapat diakses oleh satu User ID yang sah. Cari bot **@userinfobot** di Telegram, kirim pesan apa saja, dan catat **ID** numerik Anda (misalnya: `123456789`). ID ini digunakan sebagai `ALLOWED_TELEGRAM_USER_ID`.

---

### 2. Setup GitHub Personal Access Token (PAT)
Bot membutuhkan token GitHub untuk melakukan clone repo, push branch, membuat Pull Request, serta melakukan merge PR secara otomatis.

1. Masuk ke akun GitHub Anda.
2. Pergi ke **Settings** -> **Developer Settings** -> **Personal Access Tokens** -> **Tokens (classic)** (atau gunakan Fine-grained tokens).
3. Klik **Generate new token**.
4. Berikan hak akses (scopes) berikut:
   - `repo` (Akses penuh untuk repositori privat dan publik, commit, push, PR, merge)
   - `workflow` (Opsional, jika ada GitHub Actions yang terpicu)
5. Klik **Generate token** dan salin token tersebut (misalnya: `ghp_xxxxxxxxxxxx`). Token ini akan dimasukkan ke `GITHUB_TOKEN` di `.env`.

---

### 3. Setup Google Cloud Platform (GCP) & Vertex AI
Bot menggunakan SDK GenAI Google terbaru (`google-genai`) dengan fitur Vertex AI diaktifkan untuk memproses prompt dan gambar.

#### Langkah A: Membuat Project GCP & Mengaktifkan Vertex AI
1. Masuk ke [Google Cloud Console](https://console.cloud.google.com/).
2. Buat project baru atau pilih project yang sudah ada. Catat **Project ID** Anda (misalnya: `my-gcp-project-123`).
3. Pada kolom pencarian console, cari **Vertex AI API** dan klik **Enable**.

#### Langkah B: Membuat Service Account & Mengunduh JSON Key
Untuk mengizinkan bot mengakses Vertex AI GCP secara aman dari luar infrastruktur GCP (misalnya dari server lokal Anda), Anda harus menggunakan Service Account:

1. Di GCP Console, navigasikan ke **IAM & Admin** -> **Service Accounts**.
2. Klik **Create Service Account** di bagian atas.
3. Beri nama service account (contoh: `telegram-ai-agent`) lalu klik **Create and Continue**.
4. Di bagian **Grant this service account access to project**, pilih Role:
   - **Vertex AI User** (`roles/aiplatform.user`) -> Penting untuk menjalankan API Gemini melalui Vertex AI.
5. Klik **Continue**, lalu klik **Done**.
6. Setelah kembali ke daftar Service Accounts, klik service account yang baru dibuat, masuk ke tab **Keys**.
7. Klik **Add Key** -> **Create new key**. Pilih format **JSON** dan klik **Create**.
8. File JSON key akan terunduh otomatis ke komputer Anda. Simpan file ini dengan aman di folder project Anda (misal beri nama `gcp-key.json`). **Jangan pernah melakukan commit file ini ke GitHub!**

#### Langkah C: Autentikasi GCP di Mesin Lokal
Untuk menjalankan bot, Anda memiliki dua cara untuk memberi tahu Google SDK tentang credentials Anda:

* **Opsi 1 (Direkomendasikan)**: Set path file JSON key pada environment variable `GOOGLE_APPLICATION_CREDENTIALS` di dalam file `.env`:
  ```env
  GOOGLE_APPLICATION_CREDENTIALS="/path/ke/folder/project/gcp-key.json"
  ```
* **Opsi 2 (Menggunakan gcloud CLI)**: Jika Anda menginstal Google Cloud SDK (`gcloud`) di mesin Anda, Anda cukup menjalankan perintah berikut di terminal Anda untuk mengautentikasi:
  ```bash
  gcloud auth application-default login
  ```
  SDK Google secara otomatis akan mendeteksi kredensial tersebut tanpa perlu mengisi variabel `GOOGLE_APPLICATION_CREDENTIALS`.

---

## 📝 Konfigurasi Environment File (`.env`)

Salin file `.env.example` menjadi `.env` di direktori utama proyek:

```bash
cp .env.example .env
```

Isi variabel di dalam file `.env` sebagai berikut:

```env
# Telegram Configuration
TELEGRAM_BOT_TOKEN="isi_dengan_token_dari_botfather"
ALLOWED_TELEGRAM_USER_ID=123456789  # Ganti dengan ID telegram Anda

# GitHub Configuration
GITHUB_TOKEN="isi_dengan_github_pat_anda"
BACKEND_REPO="username_atau_org/nama_repo_backend" # Contoh: omdika/oura-studio-backend
IOS_REPO="username_atau_org/nama_repo_ios"         # Kosongkan jika tidak memakai iOS repo

# Workspace & GCP Project
WORKSPACE_DIR="./workspace"  # Tempat bot melakukan git clone & edit file secara lokal
GCP_PROJECT_ID="isi_dengan_project_id_gcp_anda"

# Opsional: Jika menggunakan JSON key Service Account secara langsung
GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/ke/gcp-key.json"
```

---

## 🚀 Cara Menjalankan Bot

### Opsi A: Menjalankan secara Lokal

1. **Persiapkan Python Virtual Environment (Python 3.10+)**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Untuk macOS/Linux
   # venv\Scripts\activate   # Untuk Windows
   ```

2. **Install Dependensi**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Jalankan Bot**:
   ```bash
   python bot.py
   ```

---

### Opsi B: Menjalankan dengan Docker

Proyek ini sudah dilengkapi dengan Dockerfile dan Docker Compose untuk kemudahan deployment.

1. **Pastikan Docker & Docker Compose sudah terpasapng** di mesin Anda.
2. **Build & Run Container**:
   ```bash
   docker-compose up -d --build
   ```
3. **Cek Logs untuk Memastikan Bot Berjalan**:
   ```bash
   docker-compose logs -f
   ```

---

## 💡 Perintah Bot yang Tersedia di Telegram

Kirim perintah berikut langsung ke bot Anda di Telegram:
* `/start` : Memulai interaksi dengan bot dan mengecek otorisasi user.
* `/reset` atau `/new` : Menghapus riwayat chat aktif dan membersihkan cache snapshot codebase. Sangat berguna saat Anda ingin memulai tugas baru dengan codebase yang segar dari branch `main`.

# Shopee Live Bot

Bot otomatis untuk Shopee Live menggunakan Streamlit

## Fitur
- Manajemen akun multi
- Auto-show produk
- Pemantauan chatroom
- Logging aktivitas
- Persistensi data

## Cara Deploy di Streamlit Cloud
1. Fork repositori ini
2. Tambahkan secrets:
   - `STREAMLIT_SERVER_PORT=8501`
3. Upload file accounts.txt melalui interface web
4. Aktifkan deployment otomatis dari GitHub

## Konfigurasi Lokal
1. Clone repositori
2. Buat virtual environment:
   ```bash
   python -m venv env
   source env/bin/activate
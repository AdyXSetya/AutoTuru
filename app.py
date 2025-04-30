import streamlit as st
import time
import json
import requests
import threading
from datetime import datetime
import re
import os

# Konfigurasi
st.set_page_config(page_title="Shopee Live Bot", page_icon="🛒")
STATE_FILE = 'bot_state.json'

# Inisialisasi session state dengan JSON
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return {
                    'accounts': data.get('accounts', []),
                    'running': data.get('running', False),
                    'logs': data.get('logs', [])
                }
        except json.JSONDecodeError:
            return {'accounts': [], 'running': False, 'logs': []}
    return {'accounts': [], 'running': False, 'logs': []}

state = load_state()
for key, value in state.items():
    if key not in st.session_state:
        st.session_state[key] = value

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump({
            'accounts': st.session_state.accounts,
            'running': st.session_state.running,
            'logs': st.session_state.logs
        }, f, indent=2)

# Fungsi logging dengan auto-save
def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    st.session_state.logs.append(log_entry)
    if len(st.session_state.logs) > 200:
        st.session_state.logs.pop(0)
    save_state()  # Auto-save setiap log

# Fungsi load akun
def load_accounts(uploaded_file):
    add_log("Memulai load accounts")
    accounts = []
    try:
        content = uploaded_file.getvalue().decode('utf-8')
        for line in content.splitlines():
            line = line.strip()
            if line:
                parts = line.split(',', 1)
                if len(parts) != 2:
                    add_log(f"Invalid line: {line}")
                    continue
                username, cookie = parts
                accounts.append({
                    'username': username.strip(),
                    'cookie': cookie.strip(),
                    'session_id': None,
                    'chatroom_id': None,
                    'etalase': [],
                    'last_show_time': time.time(),
                    'last_session_check': 0,
                    'last_etalase_check': 0
                })
        add_log(f"Loaded {len(accounts)} akun")
    except Exception as e:
        add_log(f"Error loading accounts: {str(e)}")
    save_state()  # Simpan setelah load akun
    return accounts

# Fungsi proses cookie
def process_cookie(cookie):
    fixed_cookie = "SPC_F=fdecd079d2e0d109_unknown;SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2"
    c1 = {k.strip(): v.strip() for k, v in (pair.split('=') for pair in fixed_cookie.split(';') if '=' in pair)}
    c2 = {k.strip(): v.strip() for k, v in (pair.split('=') for pair in cookie.split(';') if '=' in pair)}
    combined = {**c1, **c2}
    return '; '.join([f"{k}={v}" for k, v in combined.items()])

# Fungsi cek live
def check_live(cookie):
    add_log("Memulai Check_Live")
    now = datetime.utcnow().strftime('%Y-%m-%d')
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&timeDim=30d&endDate={now}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "accept": "*/*",
        "content-type": "application/json",
        "Cookie": cookie
    }
    try:
        response = requests.get(url, headers=headers)
        add_log(f"Response Check_Live: {response.status_code}")
        data = response.json()
        if data.get('code') == 0 and data['data']['list']:
            if data['data']['list'][0]['status'] == '1':
                return data['data']['list'][0]['sessionId']
    except Exception as e:
        add_log(f"Check_Live Error: {str(e)}")
    return None

# Fungsi dapatkan chatroom ID
def get_chatroom_id(session_id, cookie):
    add_log("Memulai get_chatroom_id")
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}"
    headers = {
        "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61",
        "accept": "*/*",
        "content-type": "application/json",
        "Cookie": cookie
    }
    try:
        response = requests.get(url, headers=headers)
        add_log(f"Response get_chatroom_id: {response.status_code}")
        data = response.json()
        return data.get('data', {}).get('session', {}).get('chatroom_id')
    except Exception as e:
        add_log(f"get_chatroom_id Error: {str(e)}")
    return None

# Fungsi cek etalase
def check_etalase(session_id, cookie):
    add_log("Memulai check_etalase")
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/host/items?limit=100&offset=0"
    headers = {
        "User-Agent": "okhttp/3.12.4 app_type=1",
        "accept": "*/*",
        "content-type": "application/json",
        "Cookie": cookie
    }
    try:
        response = requests.get(url, headers=headers)
        add_log(f"Response check_etalase: {response.status_code}")
        data = response.json()
        if data.get('err_code') == 0 and data.get('data', {}).get('items'):
            items = []
            for idx, item in enumerate(data['data']['items'], 1):
                name = item.get('name', '').replace('|', '').replace('\n', '')
                items.append({
                    'no': idx,
                    'item_id': item['item_id'],
                    'shop_id': item['shop_id'],
                    'name': name
                })
            return items
    except Exception as e:
        add_log(f"check_etalase Error: {str(e)}")
    return []

# Fungsi show produk
def show_produk(item_id, shop_id, session_id, cookie):
    add_log(f"Memulai show_produk: item_id={item_id}, shop_id={shop_id}")
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/show"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "accept": "*/*",
        "Content-Type": "application/json",
        "Cookie": cookie
    }
    payload = json.dumps({"item": json.dumps({"item_id": item_id, "shop_id": shop_id})})
    try:
        response = requests.post(url, headers=headers, data=payload)
        add_log(f"Response show_produk: {response.status_code}")
        return response.text
    except Exception as e:
        add_log(f"show_produk Error: {str(e)}")
    return None

# Fungsi ambil pesan
def get_messages(chatroom_id):
    add_log("Memulai get_messages")
    url = f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message"
    headers = {
        "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61",
        "accept": "*/*",
        "Content-Type": "application/json",
        "Cookie": "AC_CERT_D=U2FsdGVkX1+UjZ0kttfkY9XG2BE2mX0s99kii5W9wZzdr8ZlexScqt0F17ZPjGud+nFw3J/P+o6kJ3XYhTXzSkCKzLML+rfyQJev0QwOfz4QxwWK83TcArOBXzdlurBNu1FPm2qpAHcjbdgJNJRwbRpqEcFxkOG4oUPOCodVQLf1/gfmOmifZ4Uh07wYQUIhuIfxHIAP+GSI/cYFhl/xjwqIc82BAPcHDMZw6oaKTs271YZGP4/y6l/idrais5DuqJ/O4svFAZYCGWmi576M3QH7Xmfo6yeY5TPrxYvoH1m6TshoSeQh6/Vh5cobpc0uP/Cmx5yG/6EVY4b3NLUKzQIdU9/Ai6l+duKULPdIf9UXUjv2oVEgf2/3p8a0tq8nI58h4j00BmE/LIBDPbWwO1UYj0iCjkwAxZh1Wgq2dljHMu6w5gYK5M9DeH4oPOEmxs8sXy0SpP+nEsw46xf8xErzGuqiKh1YUgQsGgkfqkZMts5JFu6QSBuRYzn5ZpfJ0g+hF8ZNGPRnkF4ud+oM1AKl/08q76zcBUTVjpr49gmznBfCNTfnudjDR9zp2CESYByzvIt12VuPd2W3rbXkOnXHIUOZ0jgKTsZywgjWFqqh31sSKOTG9/cdkPD1tSrBW6j0isbPTtMVTOXBag9sErR5a1oJfEAT1bHz75v0XCg3Ui9jWQERliNjCxES8PiBfRV6rPQr5JpxOjwdx4G9zFFXaj5pORoyKC0qtOJETtbeFMJLg1xw3900od65tLJBgILFfvP4WVlc+6BBKXGtGx3sr+BcFLs3gECCYn2VhchbzLN5kY6OLRXjsV6rDx/wMB/ZWb5l2M2CCjaoYbNbkXKo0rcbm7bGLnwSWsWgxcfd98pnoCY3bwvHwKHQNMbzi+F/Gs0MoDRWTU4eM5EysH5TSms6/DjxqEr7OJT3wQoFQifJ+Yy4ifzzJrThnG8Bn6NkVVm3GsJvGZD1DBzbn2MikszXXHE50yZoAHbvK19vOt3GuOzCVFwfBUcCs1wjp3gOk6hbzwUePX15cLfVwOGJPpbFrkhbDuEu9p6x+0Qu1e2kVt77w1vb0dyiB+WZtkaMw0s0ryLzYokeDHl9hQ==; userid=0; language=id; shopee_token=null; username=null; UA=Shopee%20Android%20Beeshop%20locale%2Fid%20version%3D715%20appver%3D29552; shopee_token=null; shopee_app_version=29552; SPC_SI=l28HaAAAAAB1a1LabnFVWh8nHAAAAAAAR2ZURTZMeFk=; SPC_CLIENTID=QIzdI9wlYOJ3j0nWgjnlvtweoecpxkht; SPC_U=-; SPC_EC=-; SPC_SEC_SI=v1-clhiY0E3VjJEZVI1UGhBbCpd6V3EVBQwDUvbP7Mes6QTwtNT1S8+p141WtNm2XXc7lHE4bZLGt85O61wAVaxAjtjqLncNuf9ebBQG1/a//4=; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2; SPC_R_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_R_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; REC_T_ID=847efb3a-210f-11f0-8be5-8eda1ff0b17a; SPC_T_IV=emcwalVSR1pGUGhXQWdFSA==; language=id; SPC_RNBV=5060005; SPC_DID=QIzdI9wlYOJ3j0nWKf1Md0YiBVu18dYRcSk0nsmt110=; SPC_F=fdecd079d2e0d109_unknown; SPC_F=fdecd079d2e0d109_unknown; csrftoken=1fbUbQ4dZaivBwegGRucv3Kg1YlYYIPd; shopee_rn_version=1667373194; SPC_EC=-; SPC_R_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_R_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_SI=l28HaAAAAAB1a1LabnFVWh8nHAAAAAAAR2ZURTZMeFk=; SPC_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_U=-"
    }
    try:
        response = requests.get(url, headers=headers)
        add_log(f"Response get_messages: {response.status_code}")
        return response.json()
    except Exception as e:
        add_log(f"get_messages Error: {str(e)}")
    return {}

# Fungsi deteksi nomor etalase
def detect_number(text):
    pattern = r'\b([1-9]\d?|100)\b'
    match = re.search(pattern, text)
    return int(match.group()) if match else None

# Main loop dengan auto-save
def main_loop():
    while st.session_state.running:
        try:
            for account in st.session_state.accounts:
                # Proses utama (tetap seperti sebelumnya)
                # ...
                
            save_state()  # Simpan state setiap iterasi
        except Exception as e:
            add_log(f"Critical error: {str(e)}")
            save_state()  # Pastikan tetap simpan saat error
        time.sleep(5)

# Antarmuka Streamlit
st.title("Shopee Live Bot")

uploaded_file = st.sidebar.file_uploader("Upload accounts.txt", type="txt")
start_button = st.sidebar.button("Start" if not st.session_state.running else "Restart")
stop_button = st.sidebar.button("Stop")

if start_button and not st.session_state.running:
    if uploaded_file:
        st.session_state.accounts = load_accounts(uploaded_file)
        st.session_state.running = True
        threading.Thread(target=main_loop, daemon=True).start()
        add_log("Bot started")
    else:
        st.warning("Upload accounts.txt terlebih dahulu")

if stop_button:
    st.session_state.running = False
    save_state()  # Pastikan state tersimpan saat stop
    add_log("Bot stopped")

# Tampilan status dan log
st.subheader("Account Status")
for account in st.session_state.accounts:
    status = "Live" if account.get('session_id') else "Offline"
    st.write(f"**{account['username']}** - {status}")

st.subheader("Logs")
log_container = st.empty()

while True:
    with log_container.container():
        st.write('\n'.join(st.session_state.logs[-20:]))
    time.sleep(1)

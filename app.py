import streamlit as st
import requests
import json
import time
import threading
import re
import random
from datetime import datetime
from collections import deque

# Konfigurasi
ACCOUNTS_URL = "https://raw.githubusercontent.com/AdyXSetya/AutoTuru/refs/heads/main/accounts.txt"
LOG_FILE = "bot.log"
CHECK_INTERVAL = 5
ACCOUNT_REFRESH_INTERVAL = 300

# Inisialisasi Streamlit
st.set_page_config(page_title="Shopee Live Bot", page_icon="🤖")
st.title("Shopee Live Bot v6")
status_text = st.empty()
log_container = st.empty()
stop_button = st.button("Stop Bot")

# Variabel global
accounts = []
running = True
last_account_refresh = 0

# Session state untuk log
if 'logs' not in st.session_state:
    st.session_state.logs = deque(maxlen=200)

def log(message, username=None):
    """Fungsi logging dengan format: [waktu] [username] pesan"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}]"
    if username:
        log_entry += f" [{username}]"
    log_entry += f" {message}"
    
    # Simpan ke file
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Error writing log: {str(e)}")
    
    # Simpan ke session state
    st.session_state.logs.append(log_entry)

def load_accounts():
    """Ambil accounts.txt dari GitHub"""
    try:
        res = requests.get(ACCOUNTS_URL)
        res.raise_for_status()
        lines = res.text.strip().split('\n')
        accounts = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(',', 1)
                if len(parts) >= 2:
                    username, cookie = parts[0].strip(), ','.join(parts[1:]).strip()
                    accounts.append({
                        'username': username,
                        'cookie': cookie,
                        'session_id': None,
                        'chatroom_id': None,
                        'etalase': [],
                        'last_show_time': time.time(),
                        'last_session_check': 0,
                        'last_etalase_check': 0
                    })
        log(f"Akun diperbarui ({len(accounts)} akun)", "SYSTEM")
        return accounts
    except Exception as e:
        log(f"Gagal memuat akun: {str(e)}", "ERROR")
        return []

def cookie_sakti(cookie):
    """Gabungkan cookie tambahan"""
    base = "SPC_F=fdecd079d2e0d109_unknown;SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2"
    combined = {}

    # Proses base cookie
    for part in base.split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            combined[k.strip()] = v.strip()

    # Tambahkan cookie dari akun
    for part in cookie.split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            combined[k.strip()] = v.strip()

    return '; '.join([f"{k}={v}" for k, v in combined.items()])

def check_live(cookie):
    """Cek status live"""
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2"
    params = {
        'page': 1,
        'pageSize': 1000,
        'endDate': now
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1',
        'Cookie': cookie
    }
    
    try:
        res = requests.get(url, params=params, headers=headers)
        data = res.json()
        if data.get('code') == 0 and data['data']['list']:
            if data['data']['list'][0]['status'] == '1':
                return data['data']['list'][0]['sessionId']
    except Exception as e:
        log(f"Check live error: {str(e)}", "SYSTEM")
    return None

def get_chatroom_id(session_id, cookie):
    """Dapatkan chatroom ID"""
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}"
    headers = {
        'User-Agent': 'Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61',
        'Cookie': cookie
    }
    
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        return data['data']['session']['chatroom_id']
    except Exception as e:
        log(f"Get chatroom error: {str(e)}", "SYSTEM")
        return None

def check_etalase(session_id, cookie):
    """Cek etalase produk"""
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/host/items"
    params = {
        'limit': 100,
        'offset': 0
    }
    headers = {
        'User-Agent': 'okhttp/3.12.4 app_type=1',
        'Cookie': cookie
    }
    
    try:
        res = requests.get(url, params=params, headers=headers)
        data = res.json()
        if data.get('err_code') == 0 and data['data']['items']:
            items = []
            for idx, item in enumerate(data['data']['items'], 1):
                items.append({
                    'no': idx,
                    'item_id': item['item_id'],
                    'shop_id': item['shop_id'],
                    'name': item['name'].replace("|", "")
                })
            return items
    except Exception as e:
        log(f"Check etalase error: {str(e)}", "SYSTEM")
    return []

def show_produk(item_id, shop_id, session_id, cookie):
    """Tampilkan produk"""
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/show"
    payload = json.dumps({
        "item": json.dumps({"item_id": item_id, "shop_id": shop_id})
    })
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1',
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    
    try:
        res = requests.post(url, data=payload, headers=headers)
        return res.text
    except Exception as e:
        log(f"Show produk error: {str(e)}", "SYSTEM")
        return "Error"

def detect_number(text):
    """Deteksi nomor dari pesan"""
    numbers = list(map(int, re.findall(r'\d+', text)))
    for num in numbers:
        if 1 <= num <= 100:
            return num
    return None

def process_message(account, message):
    """Proses pesan chat"""
    try:
        content = json.loads(message.get('content', '{}'))
        # Cek pesan dengan item_id dan shop_id
        if 'item_id' in content and 'shop_id' in content:
            result = show_produk(
                content['item_id'],
                content['shop_id'],
                account['session_id'],
                account['cookie']
            )
            log(f"AUTO SHOW: {result}", account['username'])
            account['last_show_time'] = time.time()
            return
        
        # Cek pesan dengan nomor etalase
        text = content.get('content', '')
        number = detect_number(text)
        if number and 1 <= number <= 100:
            if number <= len(account['etalase']):
                item = account['etalase'][number-1]
                result = show_produk(
                    item['item_id'],
                    item['shop_id'],
                    account['session_id'],
                    account['cookie']
                )
                log(f"AUTO SHOW #{number}: {item['name']} - {result}", account['username'])
                account['last_show_time'] = time.time()
    
    except Exception as e:
        log(f"Pesan processing error: {str(e)}", account['username'])

def bot_loop():
    global accounts, last_account_refresh, running
    
    while running:
        try:
            # Refresh accounts setiap 5 menit
            if time.time() - last_account_refresh > ACCOUNT_REFRESH_INTERVAL:
                new_accounts = load_accounts()
                if new_accounts:
                    accounts = new_accounts
                    last_account_refresh = time.time()

            for account in accounts:
                try:
                    # Periksa session
                    if time.time() - account['last_session_check'] > 3600:
                        account['session_id'] = check_live(account['cookie'])
                        if account['session_id']:
                            account['chatroom_id'] = get_chatroom_id(
                                account['session_id'],
                                account['cookie']
                            )
                        else:
                            account['chatroom_id'] = None
                        account['last_session_check'] = time.time()

                    # Periksa etalase
                    if account['session_id'] and time.time() - account['last_etalase_check'] > 7200:
                        cookie = cookie_sakti(account['cookie'])
                        etalase = check_etalase(account['session_id'], cookie)
                        account['etalase'] = etalase if etalase else []
                        account['last_etalase_check'] = time.time()
                        log(f"Etalase diperbarui ({len(account['etalase'])} items)", account['username'])

                    # Proses chat
                    if account['chatroom_id']:
                        url = f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{account['chatroom_id']}/message"
                        headers = {
                            'User-Agent': 'Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61',
                            'Cookie': 'SPC_U=-'
                        }
                        try:
                            res = requests.get(url, headers=headers)
                            messages = res.json().get('data', {}).get('message', [])
                            for msg in messages:
                                for sub_msg in msg.get('msgs', []):
                                    log(f"{sub_msg['nickname']}: {sub_msg.get('content', '')}", account['username'])
                                    process_message(account, sub_msg)
                        except Exception as e:
                            log(f"Chat error: {str(e)}", account['username'])

                    # Auto show jika idle
                    if time.time() - account['last_show_time'] > 200 and account['etalase']:
                        item = random.choice(account['etalase'])
                        result = show_produk(
                            item['item_id'],
                            item['shop_id'],
                            account['session_id'],
                            account['cookie']
                        )
                        log(f"AUTO SHOW #{item['no']}: {item['name']} - {result}", account['username'])
                        account['last_show_time'] = time.time()

                except Exception as e:
                    log(f"Account error: {str(e)}", account['username'])

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log(f"Critical error: {str(e)}", "SYSTEM")
            time.sleep(10)

# Thread untuk menjalankan bot
thread = threading.Thread(target=bot_loop)
thread.start()

# Tampilkan log real-time
while running:
    with log_container:
        st.text('\n'.join(st.session_state.logs))
    time.sleep(1)

# Handler tombol stop
if stop_button:
    running = False
    log("Bot stopped by user", "SYSTEM")
    st.warning("Bot stopped")

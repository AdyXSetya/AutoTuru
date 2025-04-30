import streamlit as st
import requests
import json
import time
import threading
import re
import random
from datetime import datetime

# Konfigurasi
ACCOUNTS_URL = "https://raw.githubusercontent.com/AdyXSetya/AutoTuru/refs/heads/main/accounts.txt"
LOG_FILE = "bot.log"
CHECK_INTERVAL = 5
ACCOUNT_REFRESH_INTERVAL = 300

# Streamlit interface
st.title("Shopee Live Bot v4")
status_text = st.empty()
log_container = st.empty()  # Container untuk log real-time
stop_button = st.button("Stop Bot")

# Variabel global
accounts = []
running = True
last_account_refresh = 0
log_entries = []  # Menyimpan log sementara untuk tampilan

def log(message, username=None):
    """Fungsi logging dengan update UI real-time"""
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
    
    # Simpan ke buffer untuk UI
    log_entries.append(log_entry)
    if len(log_entries) > 100:  # Batasi jumlah log di memori
        log_entries.pop(0)
    
    # Update UI
    with log_container.container():
        st.text('\n'.join(log_entries[-20:]))

def load_accounts():
    """Ambil accounts.txt dari GitHub"""
    try:
        res = requests.get(ACCOUNTS_URL)
        res.raise_for_status()
        lines = res.text.strip().split('\n')
        accounts = []
        for line in lines:
            if line.strip() and not line.startswith('#'):
                parts = line.strip().split(',', 1)
                if len(parts) == 2:
                    username, cookie = parts
                    accounts.append({
                        'username': username.strip(),
                        'cookie': cookie.strip(),
                        'session_id': None,
                        'chatroom_id': None,
                        'etalase': [],
                        'last_show': time.time(),
                        'last_session_check': 0,
                        'last_etalase_check': 0
                    })
        log(f"Akun diperbarui ({len(accounts)} akun) dari GitHub", "SYSTEM")
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
            k = k.strip()
            combined[k] = v.strip()  # Timpa jika sudah ada
    
    return '; '.join([f"{k}={v}" for k, v in combined.items()])

def check_live(cookie):
    """Cek status live"""
    url = "https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2"
    params = {
        'page': 1,
        'pageSize': 1000,
        'endDate': datetime.now().strftime("%Y-%m-%d")
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
        log(f"Check live error: {str(e)}")
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
    except:
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
        if data.get('err_code') == 0:
            items = []
            for idx, item in enumerate(data['data']['items'], 1):
                items.append({
                    'no': idx,
                    'item_id': item['item_id'],
                    'shop_id': item['shop_id'],
                    'name': item['name'].replace("|", "")
                })
            return items
    except:
        pass
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
    except:
        return "Error"

def process_message(account, message):
    """Proses pesan chat"""
    try:
        content = json.loads(message.get('content', '{}'))
        if 'item_id' in content and 'shop_id' in content:
            result = show_produk(
                content['item_id'],
                content['shop_id'],
                account['session_id'],
                account['cookie']
            )
            log(f"[{account['username']}] AUTO SHOW: {result}")
            account['last_show'] = time.time()
            return
        
        # Cek nomor etalase
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
                log(f"[{account['username']}] AUTO SHOW #{number}: {item['name']} - {result}")
                account['last_show'] = time.time()
    except Exception as e:
        log(f"Message processing error: {str(e)}")

def detect_number(text):
    """Deteksi nomor dari pesan"""
    numbers = list(map(int, re.findall(r'\d+', text)))
    for num in numbers:
        if 1 <= num <= 100:
            return num
    return None

def log(message):
    """Tambahkan log ke container Streamlit"""
    with log_container:
        st.text(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def bot_loop():
    global accounts, last_account_refresh
    
    while running:
        try:
            # Refresh accounts jika sudah waktunya
            if time.time() - last_account_refresh > ACCOUNT_REFRESH_INTERVAL:
                new_accounts = load_accounts()
                if new_accounts:
                    accounts = new_accounts
                    last_account_refresh = time.time()

            for account in accounts:
                try:
                    # Cek session
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
                        log(f"Session diperbarui: {account['session_id']}", account['username'])

                    # Cek etalase
                    if account['session_id'] and time.time() - account['last_etalase_check'] > 7200:
                        cookie = cookie_sakti(account['cookie'])
                        etalase = check_etalase(account['session_id'], cookie)
                        account['etalase'] = etalase or []
                        account['last_etalase_check'] = time.time()
                        log(f"Etalase diperbarui ({len(etalase)} items)", account['username'])

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
                    if time.time() - account['last_show'] > 200 and account['etalase']:
                        item = random.choice(account['etalase'])
                        result = show_produk(
                            item['item_id'],
                            item['shop_id'],
                            account['session_id'],
                            account['cookie']
                        )
                        log(f"AUTO SHOW #{item['no']}: {item['name']} - {result}", account['username'])
                        account['last_show'] = time.time()

                except Exception as e:
                    log(f"Error processing: {str(e)}", account['username'])

            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            log(f"Critical error: {str(e)}", "SYSTEM")
            time.sleep(10)

# Jalankan bot di thread terpisah
thread = threading.Thread(target=bot_loop)
thread.start()

# Handler tombol stop
if stop_button:
    running = False
    log("Bot stopped by user", "SYSTEM")
    st.warning("Bot stopped")

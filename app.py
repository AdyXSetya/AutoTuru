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

# Inisialisasi session state
if 'logs' not in st.session_state:
    st.session_state.logs = deque(maxlen=100)

# Streamlit interface
st.title("Shopee Live Bot v5")
status_text = st.empty()
log_placeholder = st.empty()  # Placeholder untuk log
stop_button = st.button("Stop Bot")

# Variabel global
accounts = []
running = True
last_account_refresh = 0

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
    
    # Update session state
    st.session_state.logs.append(log_entry)

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
                            'Cookie': 'AC_CERT_D=U2FsdGVkX1+UjZ0kttfkY9XG2BE2mX0s99kii5W9wZzdr8ZlexScqt0F17ZPjGud+nFw3J/P+o6kJ3XYhTXzSkCKzLML+rfyQJev0QwOfz4QxwWK83TcArOBXzdlurBNu1FPm2qpAHcjbdgJNJRwbRpqEcFxkOG4oUPOCodVQLf1/gfmOmifZ4Uh07wYQUIhuIfxHIAP+GSI/cYFhl/xjwqIc82BAPcHDMZw6oaKTs271YZGP4/y6l/idrais5DuqJ/O4svFAZYCGWmi576M3QH7Xmfo6yeY5TPrxYvoH1m6TshoSeQh6/Vh5cobpc0uP/Cmx5yG/6EVY4b3NLUKzQIdU9/Ai6l+duKULPdIf9UXUjv2oVEgf2/3p8a0tq8nI58h4j00BmE/LIBDPbWwO1UYj0iCjkwAxZh1Wgq2dljHMu6w5gYK5M9DeH4oPOEmxs8sXy0SpP+nEsw46xf8xErzGuqiKh1YUgQsGgkfqkZMts5JFu6QSBuRYzn5ZpfJ0g+hF8ZNGPRnkF4ud+oM1AKl/08q76zcBUTVjpr49gmznBfCNTfnudjDR9zp2CESYByzvIt12VuPd2W3rbXkOnXHIUOZ0jgKTsZywgjWFqqh31sSKOTG9/cdkPD1tSrBW6j0isbPTtMVTOXBag9sErR5a1oJfEAT1bHz75v0XCg3Ui9jWQERliNjCxES8PiBfRV6rPQr5JpxOjwdx4G9zFFXaj5pORoyKC0qtOJETtbeFMJLg1xw3900od65tLJBgILFfvP4WVlc+6BBKXGtGx3sr+BcFLs3gECCYn2VhchbzLN5kY6OLRXjsV6rDx/wMB/ZWb5l2M2CCjaoYbNbkXKo0rcbm7bGLnwSWsWgxcfd98pnoCY3bwvHwKHQNMbzi+F/Gs0MoDRWTU4eM5EysH5TSms6/DjxqEr7OJT3wQoFQifJ+Yy4ifzzJrThnG8Bn6NkVVm3GsJvGZD1DBzbn2MikszXXHE50yZoAHbvK19vOt3GuOzCVFwfBUcCs1wjp3gOk6hbzwUePX15cLfVwOGJPpbFrkhbDuEu9p6x+0Qu1e2kVt77w1vb0dyiB+WZtkaMw0s0ryLzYokeDHl9hQ==; userid=0; language=id; shopee_token=null; username=null; UA=Shopee%20Android%20Beeshop%20locale%2Fid%20version%3D715%20appver%3D29552; shopee_token=null; shopee_app_version=29552; SPC_SI=l28HaAAAAAB1a1labnFVWh8nHAAAAAAAR2ZURTZMeFk=; SPC_CLIENTID=QIzdI9wlYOJ3j0nWgjnlvtweoecpxkht; SPC_U=-; SPC_EC=-; SPC_SEC_SI=v1-clhiY0E3VjJEZVI1UGhBbCpd6V3EVBQwDUvbP7Mes6QTwtNT1S8+p141WtNm2XXc7lHE4bZLGt85O61wAVaxAjtjqLncNuf9ebBQG1/a//4=; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2; SPC_R_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_R_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; REC_T_ID=847efb3a-210f-11f0-8be5-8eda1ff0b17a; SPC_T_IV=emcwalVSR1pGUGhXQWdFSA==; language=id; SPC_RNBV=5060005; SPC_DID=QIzdI9wlYOJ3j0nWKf1Md0YiBVu18dYRcSk0nsmt110=; SPC_F=fdecd079d2e0d109_unknown; SPC_F=fdecd079d2e0d109_unknown; csrftoken=1fbUbQ4dZaivBwegGRucv3Kg1YlYYIPd; shopee_rn_version=1667373194; SPC_EC=-; SPC_R_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_R_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_SI=l28HaAAAAAB1a1labnFVWh8nHAAAAAAAR2ZURTZMeFk=; SPC_T_ID=tCpjDGKCO2W4PY+rgc5HJ8k2VkcegpeAErfNE0BrCrAPpRF8ekHEf6CgQnz7KOhDjTynAxi3OZv1mSonaWNGrUFJGcKUokMq+SBTSPBcPiC6H+b4SqmC0JcnOkO5WRwpfGTiYo9ZLLwYqQpUoI3uApD0rCwekEbXYth0MaWcDyE=; SPC_T_IV=emcwalVSR1pGUGhXQWdFSA==; SPC_U=-'
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

# Tampilkan log real-time di UI
while running:
    with log_placeholder.container():
        st.text('\n'.join(st.session_state.logs))
    time.sleep(1)

# Handler tombol stop
if stop_button:
    running = False
    log("Bot stopped by user", "SYSTEM")
    st.warning("Bot stopped")

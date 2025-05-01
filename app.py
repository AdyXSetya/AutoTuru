import streamlit as st
import requests
import time
import threading
from datetime import datetime, timedelta
import json

# Inisialisasi session state
if 'chat_running' not in st.session_state:
    st.session_state.chat_running = False
if 'last_comments' not in st.session_state:
    st.session_state.last_comments = []
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'etalase_data' not in st.session_state:
    st.session_state.etalase_data = []

# Fungsi CookieSakti
def cookie_sakti(input_cookie):
    cookie_patch = 'SPC_F=fdecd079d2e0d109_unknown; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2'
    
    def parse_cookie(cookie_str):
        items = {}
        for part in cookie_str.split(';'):
            if '=' in part:
                key, value = part.split('=', 1)
                items[key.strip()] = value.strip()
        return items

    patch_cookies = parse_cookie(cookie_patch)
    input_cookies = parse_cookie(input_cookie)
    
    final_cookie = {**input_cookies, **patch_cookies}
    return '; '.join([f"{k}={v}" for k, v in final_cookie.items()])

# Fungsi untuk cek live dan dapatkan session ID
def check_live(cookie):
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "Cookie": cookie
    }
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            session_id = data["data"]["list"][0].get("sessionId")
            live_status = data["data"]["list"][0].get("status")
            
            return {
                "status": "SEDANG LIVE" if live_status == 1 else "TIDAK LIVE",
                "session_id": session_id if live_status == 1 else None
            }
        else:
            return {"status": "Gagal mendapatkan data live"}
    except Exception as e:
        return {"status": f"Error: {str(e)}"}

# Fungsi untuk mendapatkan chatroom ID
def get_chatroom_id(session_id, cookie):
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}"
    headers = {
        "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61",
        "Cookie": cookie
    }
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data.get('data', {}).get('session', {}).get('chatroom_id')
    except:
        return None

# Fungsi untuk mendapatkan pesan
def get_messages(chatroom_id):
    url = f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message"
    headers = {
        "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61"
    }
    
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except:
        return None

# Fungsi untuk mendapatkan etalase
def check_etalase(session_id, cookie):
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/host/items?limit=100&offset=0"
    headers = {
        "User-Agent": "okhttp/3.12.4 app_type=1",
        "Cookie": cookie
    }
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data.get("err_code") == 0 and data.get("data", {}).get("items"):
            items = []
            for idx, item in enumerate(data["data"]["items"], 1):
                items.append({
                    "no": idx,
                    "item_id": item.get("item_id"),
                    "shop_id": item.get("shop_id"),
                    "name": item.get("name", "").replace("|", "").replace("\n", "")
                })
            return items
        else:
            return None
    except:
        return None

# Fungsi untuk memproses pesan
def process_messages():
    while st.session_state.chat_running:
        if 'chatroom_id' in st.session_state:
            messages_data = get_messages(st.session_state.chatroom_id)
            
            if messages_data and messages_data.get('code') == 0:
                messages = messages_data.get('data', {}).get('message', [])
                
                for message_group in messages:
                    for msg in message_group.get('msgs', []):
                        nickname = msg.get('nickname', 'Unknown')
                        content = msg.get('content', '')
                        
                        if content:
                            try:
                                content_data = json.loads(content).get('content', '')
                            except:
                                content_data = content
                            
                            # Cek duplikat
                            current_time = datetime.now()
                            is_duplicate = False
                            
                            # Hapus komentar yang lebih dari 30 detik
                            st.session_state.last_comments = [
                                c for c in st.session_state.last_comments 
                                if current_time - c['time'] <= timedelta(seconds=30)
                            ]
                            
                            for comment in st.session_state.last_comments:
                                if (comment['nickname'] == nickname and 
                                    comment['content'] == content_data):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                st.session_state.last_comments.append({
                                    'nickname': nickname,
                                    'content': content_data,
                                    'time': current_time
                                })
                                
                                # Simpan ke log pesan
                                st.session_state.chat_messages.insert(0, {
                                    'timestamp': current_time.strftime("%H:%M:%S"),
                                    'user': nickname,
                                    'message': content_data
                                })
            
            time.sleep(2)  # Jeda 2 detik

# UI Streamlit
st.title("Shopee Live Monitoring")

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
process_btn = st.button("Cek Status & Mulai Monitoring")

if process_btn and cookie_input:
    with st.spinner("Memproses..."):
        processed_cookie = cookie_sakti(cookie_input.strip())
        live_check = check_live(processed_cookie)
        
    if live_check.get("status") == "SEDANG LIVE":
        session_id = live_check.get("session_id")
        st.success(f"SEDANG LIVE - Session ID: {session_id}")
        
        # Dapatkan chatroom ID
        chatroom_id = get_chatroom_id(session_id, processed_cookie)
        if chatroom_id:
            st.session_state.chatroom_id = chatroom_id
            st.session_state.chat_running = True
            
            # Dapatkan data etalase
            etalase_data = check_etalase(session_id, processed_cookie)
            if etalase_data:
                st.session_state.etalase_data = etalase_data
                st.write(f"Total Produk di Etalase: {len(etalase_data)}")
                st.table(etalase_data)
            else:
                st.warning("Tidak ada data etalase ditemukan")
            
            # Jalankan thread untuk monitoring chat
            threading.Thread(
                target=process_messages,
                daemon=True
            ).start()
        else:
            st.error("Gagal mendapatkan chatroom ID")
    else:
        st.error(live_check.get("status"))

# Tampilkan pesan real-time
if st.session_state.chat_running:
    st.header("Live Chat Messages")
    st.write(f"Total Pesan: {len(st.session_state.chat_messages)}")
    st.table(st.session_state.chat_messages)

# Tombol stop
if st.session_state.chat_running:
    if st.button("Stop Monitoring"):
        st.session_state.chat_running = False
        st.experimental_rerun()

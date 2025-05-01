import streamlit as st
import requests
import time
import threading
from datetime import datetime
import json
from queue import Queue, Empty

# ================================
# INISIALISASI AWAL
# ================================
if 'monitoring' not in st.session_state:
    st.session_state.monitoring = {
        'active': False,
        'chat_messages': [],
        'last_comments': [],
        'last_update': datetime.now(),
        'thread': None
    }

DEBUG = True
message_queue = Queue()

# ================================
# FUNGSI UTILITY
# ================================
def debug_log(message):
    """Catat pesan debug ke antrian"""
    if DEBUG:
        message_queue.put({
            'type': 'debug',
            'message': f"[DEBUG] {datetime.now()} - {message}"
        })

def cookie_sakti(input_cookie):
    """Proses cookie input untuk Shopee"""
    cookie_patch = 'SPC_F=fdecd079d2e0d109_unknown; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2'
    
    def parse_cookie(cookie_str):
        items = {}
        for part in cookie_str.split(';'):
            if '=' in part:
                key, value = part.split('=', 1)
                items[key.strip()] = value.strip()
        return items
    
    final_cookie = parse_cookie(input_cookie)
    final_cookie.update(parse_cookie(cookie_patch))
    return '; '.join([f"{k}={v}" for k, v in final_cookie.items()])

# ================================
# FUNGSI MONITORING
# ================================
def check_live(cookie):
    """Cek status live Shopee"""
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"
    
    try:
        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
            "Cookie": cookie
        })
        
        data = response.json()
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            session_id = data["data"]["list"][0].get("sessionId")
            live_status = data["data"]["list"][0].get("status")
            return {
                "status": "SEDANG LIVE" if live_status == 1 else "TIDAK LIVE",
                "session_id": session_id if live_status == 1 else None
            }
        return {"status": "Gagal mendapatkan data live"}
    except Exception as e:
        return {"status": f"Error: {str(e)}"}

def get_chatroom_id(session_id, cookie):
    """Dapatkan chatroom ID dari session"""
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}"
    try:
        response = requests.get(url, headers={
            "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61",
            "Cookie": cookie
        })
        return response.json().get('data', {}).get('session', {}).get('chatroom_id')
    except Exception as e:
        debug_log(f"Error get_chatroom_id: {str(e)}")
        return None

# ================================
# WORKER THREAD
# ================================
def message_worker(chatroom_id):
    """Thread untuk memantau pesan secara real-time"""
    debug_log("Worker thread dimulai")
    consecutive_errors = 0
    
    while st.session_state.monitoring['active']:
        try:
            if not chatroom_id:
                time.sleep(1)
                continue
                
            messages_data = requests.get(
                f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message",
                headers={"User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61"},
                timeout=10
            ).json()
            
            if messages_data.get('code') == 0:
                consecutive_errors = 0
                for msg in messages_data.get('data', {}).get('messages', []):
                    nickname = msg.get('sender', {}).get('nickname', 'Unknown')
                    content = msg.get('content', '')
                    
                    if content.startswith('{'):
                        try:
                            content = json.loads(content).get('content', '')
                        except:
                            pass
                    
                    message_queue.put({
                        'type': 'chat',
                        'nickname': nickname,
                        'content': content,
                        'time': datetime.now()
                    })
            else:
                consecutive_errors += 1
                if consecutive_errors > 5:
                    break
            
            time.sleep(1)
        except Exception as e:
            consecutive_errors += 1
            debug_log(f"Error kritis: {str(e)}")
            time.sleep(5)
    
    debug_log("Worker thread berhenti")

# ================================
# PROSES ANTRIAN PESAN
# ================================
def process_queue():
    """Proses semua pesan dalam antrian"""
    current_time = datetime.now()
    new_messages = []
    
    while True:
        try:
            msg = message_queue.get_nowait()
            if msg['type'] == 'debug':
                new_messages.append({
                    'timestamp': current_time.strftime("%H:%M:%S"),
                    'user': 'SYSTEM',
                    'message': msg['message']
                })
            elif msg['type'] == 'chat':
                is_duplicate = any(
                    c['nickname'] == msg['nickname'] and
                    c['content'] == msg['content'] and
                    (current_time - c['time']).total_seconds() < 5
                    for c in st.session_state.monitoring['last_comments']
                )
                if not is_duplicate:
                    new_messages.append({
                        'timestamp': msg['time'].strftime("%H:%M:%S"),
                        'user': msg['nickname'],
                        'message': msg['content']
                    })
                    st.session_state.monitoring['last_comments'] = st.session_state.monitoring['last_comments'][-50:] + [msg]
            message_queue.task_done()
        except Empty:
            break
    
    if new_messages:
        updated_messages = new_messages + st.session_state.monitoring['chat_messages']
        st.session_state.monitoring['chat_messages'] = updated_messages[:200]
        st.session_state.monitoring['last_update'] = current_time

# ================================
# SETUP ANTARMUKA
# ================================
st.title("Shopee Live Monitoring")

# Status monitoring
status_placeholder = st.sidebar.empty()
def show_status():
    if st.session_state.monitoring['active']:
        status_placeholder.success(
            f"🔴 LIVE | Update: {st.session_state.monitoring['last_update'].strftime('%H:%M:%S')}"
        )
    else:
        status_placeholder.warning("Monitoring tidak aktif")
show_status()

# Input cookie
cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
process_btn = st.button("Cek Status & Mulai Monitoring")

if process_btn and cookie_input:
    if st.session_state.monitoring['active']:
        st.warning("Monitoring sudah berjalan!")
    else:
        processed_cookie = cookie_sakti(cookie_input.strip())
        live_check = check_live(processed_cookie)
        
        if live_check.get("status") == "SEDANG LIVE":
            session_id = live_check.get("session_id")
            chatroom_id = get_chatroom_id(session_id, processed_cookie)
            
            if chatroom_id:
                st.session_state.monitoring['active'] = True
                thread = threading.Thread(target=message_worker, args=(chatroom_id,), daemon=True)
                thread.start()
                st.session_state.monitoring['thread'] = thread
                st.success(f"Monitoring dimulai dengan Chatroom ID: {chatroom_id}")
            else:
                st.error("Gagal mendapatkan chatroom ID")
        else:
            st.error(live_check.get("status"))
    
    show_status()

# Tampilkan pesan
with st.container():
    st.header("Live Chat Messages")
    if st.session_state.monitoring['chat_messages']:
        st.write(f"Total Pesan: {len(st.session_state.monitoring['chat_messages'])}")
        st.table(st.session_state.monitoring['chat_messages'])
    else:
        st.info("Belum ada pesan masuk")

# Tombol stop
if st.session_state.monitoring['active']:
    if st.button("Stop Monitoring"):
        st.session_state.monitoring['active'] = False
        st.session_state.monitoring['chat_messages'] = []
        st.session_state.monitoring['last_comments'] = []
        st.rerun()

# Proses antrian setiap siklus
process_queue()

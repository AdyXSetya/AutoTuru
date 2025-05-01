import streamlit as st
import requests
import time
import threading
from datetime import datetime
import json
from queue import Queue, Empty

# Inisialisasi session state yang benar
if 'monitoring' not in st.session_state:
    st.session_state.monitoring = {
        'active': threading.Event(),  # Menggunakan Event bukan boolean
        'message_queue': Queue(),
        'chat_messages': [],
        'last_comments': [],
        'last_update': datetime.now(),
        'thread': None
    }

DEBUG = True

def debug_log(message):
    if DEBUG:
        st.session_state.monitoring['message_queue'].put({
            'type': 'debug',
            'message': f"[DEBUG] {datetime.now()} - {message}"
        })

def cookie_sakti(input_cookie):
    cookie_patch = 'SPC_F=fdecd079d2e0d109_unknown; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2'
    
    def parse_cookie(cookie_str):
        items = {}
        for part in cookie_str.split(';'):
            if '=' in part:
                key, value = part.split('=', 1)
                items[key.strip()] = value.strip()
        return items

    final_cookie = parse_cookie(input_cookie)
    patch_cookie = parse_cookie(cookie_patch)
    final_cookie.update(patch_cookie)
    return '; '.join([f"{k}={v}" for k, v in final_cookie.items()])

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
    except Exception as e:
        debug_log(f"Error get_chatroom_id: {str(e)}")
        return None

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
    except Exception as e:
        debug_log(f"Error check_etalase: {str(e)}")
        return None

def get_messages(chatroom_id):
    url = f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message"
    headers = {
        "User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        debug_log(f"Error get_messages: {str(e)}")
        return None

# Perbaikan utama di worker thread
def message_worker(chatroom_id, active_flag, msg_queue):
    debug_log("Worker thread dimulai")
    consecutive_errors = 0
    
    while active_flag.is_set():  # Sekarang menggunakan Event yang benar
        try:
            if not chatroom_id:
                time.sleep(1)
                continue

            messages_data = get_messages(chatroom_id)
            
            if messages_data and messages_data.get('code') == 0:
                consecutive_errors = 0
                messages = messages_data.get('data', {}).get('messages', [])
                
                for msg in messages:
                    nickname = msg.get('sender', {}).get('nickname', 'Unknown')
                    content = msg.get('content', '')
                    
                    if content.startswith('{'):
                        try:
                            content = json.loads(content).get('content', '')
                        except:
                            pass
                    
                    msg_queue.put({
                        'type': 'chat',
                        'nickname': nickname,
                        'content': content,
                        'time': datetime.now()
                    })
            else:
                consecutive_errors += 1
                if consecutive_errors > 5:
                    active_flag.clear()
                    break

            time.sleep(1)

        except Exception as e:
            consecutive_errors += 1
            debug_log(f"Error kritis: {str(e)}")
            time.sleep(5)
            
    debug_log("Worker thread berhenti")

# Setup UI
st.title("Shopee Live Monitoring")

status_placeholder = st.sidebar.empty()

def show_status():
    if st.session_state.monitoring['active'].is_set():
        status_placeholder.success(f"""
            **Status Monitoring**  
            🔴 LIVE  
            Update terakhir: {st.session_state.monitoring['last_update'].strftime('%H:%M:%S')}
        """)
    else:
        status_placeholder.warning("Monitoring tidak aktif")

show_status()

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
process_btn = st.button("Cek Status & Mulai Monitoring")

if process_btn and cookie_input:
    if st.session_state.monitoring['active'].is_set():
        st.warning("Monitoring sudah berjalan!")
    else:
        processed_cookie = cookie_sakti(cookie_input.strip())
        live_check = check_live(processed_cookie)
        
        if live_check.get("status") == "SEDANG LIVE":
            session_id = live_check.get("session_id")
            st.success(f"SEDANG LIVE - Session ID: {session_id}")
            
            etalase_data = check_etalase(session_id, processed_cookie)
            if etalase_data:
                st.write(f"Total Produk di Etalase: {len(etalase_data)}")
                st.table(etalase_data)
            else:
                st.warning("Tidak ada data etalase")
            
            chatroom_id = get_chatroom_id(session_id, processed_cookie)
            if chatroom_id:
                st.success(f"Chatroom ID: {chatroom_id}")
                st.session_state.monitoring['active'].set()  # Menggunakan Event.set()
                
                thread = threading.Thread(
                    target=message_worker,
                    args=(chatroom_id,
                          st.session_state.monitoring['active'],
                          st.session_state.monitoring['message_queue']),
                    daemon=True
                )
                thread.start()
                st.session_state.monitoring['thread'] = thread
                st.info("Monitoring dimulai...")
                debug_log("Monitoring dimulai")
            else:
                st.error("Gagal mendapatkan chatroom ID")
        else:
            st.error(live_check.get("status"))
        show_status()

def process_queue():
    current_time = datetime.now()
    
    while True:
        try:
            msg = st.session_state.monitoring['message_queue'].get_nowait()
            if msg['type'] == 'debug':
                st.session_state.monitoring['chat_messages'].insert(0, {
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
                    st.session_state.monitoring['last_comments'].append(msg)
                    st.session_state.monitoring['chat_messages'].insert(0, {
                        'timestamp': msg['time'].strftime("%H:%M:%S"),
                        'user': msg['nickname'],
                        'message': msg['content']
                    })
            st.session_state.monitoring['message_queue'].task_done()
        except Empty:
            break
    
    st.session_state.monitoring['last_update'] = current_time

process_queue()

st.header("Live Chat Messages")
if st.session_state.monitoring['chat_messages']:
    st.write(f"Total Pesan: {len(st.session_state.monitoring['chat_messages'])}")
    st.table(st.session_state.monitoring['chat_messages'])
else:
    st.info("Belum ada pesan masuk")

if st.session_state.monitoring['active'].is_set():
    if st.button("Stop Monitoring"):
        st.session_state.monitoring['active'].clear()  # Menggunakan Event.clear()
        st.session_state.monitoring['chat_messages'] = []
        st.session_state.monitoring['last_comments'] = []
        st.rerun()
        st.session_state.monitoring['last_comments'] = []
        st.rerun()

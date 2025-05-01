import streamlit as st
import requests
import time
import threading
from datetime import datetime, timedelta
import json
from queue import Queue, Empty

# Inisialisasi session state sekali di awal
if 'monitoring_params' not in st.session_state:
    st.session_state.monitoring_params = {
        'message_queue': Queue(),
        'monitoring_active': threading.Event(),
        'chat_messages': [],
        'last_comments': [],
        'etalase_data': [],
        'monitoring_thread': None
    }

DEBUG = True

# Fungsi debug yang thread-safe
def debug_log(message, message_queue):
    if DEBUG:
        message_queue.put({
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
        debug_log(f"Status Code: {response.status_code}")
        debug_log(f"Response: {response.text}")
        return response.json()
    except Exception as e:
        debug_log(f"Error get_messages: {str(e)}")
        return None

# Fungsi worker yang BENAR-BENAR terpisah dari Streamlit
def message_worker(chatroom_id, active_flag, msg_queue):
    while active_flag.is_set():
        try:
            if not chatroom_id:
                time.sleep(1)
                continue

            # Logika ambil pesan
            url = f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message"
            headers = {"User-Agent": "Android app Shopee appver=29552 app_type=1 Cronet/102.0.5005.61"}
            
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()

            if data.get('code') == 0:
                for msg in data.get('data', {}).get('messages', []):
                    nickname = msg.get('sender', {}).get('nickname', 'Unknown')
                    content = msg.get('content', '')
                    
                    # Parsing konten khusus
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
            
            time.sleep(2)
            
        except Exception as e:
            debug_log(f"Error worker: {str(e)}", msg_queue)
            time.sleep(5)

# Setup UI
st.title("Shopee Live Monitoring")

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
process_btn = st.button("Cek Status & Mulai Monitoring")

if process_btn and cookie_input:
    # Reset state jika sudah ada monitoring
    if st.session_state.monitoring_params['monitoring_active'].is_set():
        st.warning("Monitoring sudah berjalan!")
    else:
        # Proses cookie dan cek live
        processed_cookie = cookie_sakti(cookie_input.strip())
        live_check = check_live(processed_cookie)
        
        if live_check.get("status") == "SEDANG LIVE":
            session_id = live_check.get("session_id")
            st.success(f"SEDANG LIVE - Session ID: {session_id}")
            
            # Ambil data etalase
            etalase_data = check_etalase(session_id, processed_cookie)
            if etalase_data:
                st.session_state.monitoring_params['etalase_data'] = etalase_data
                st.write(f"Total Produk di Etalase: {len(etalase_data)}")
                st.table(etalase_data)
            else:
                st.warning("Tidak ada data etalase")
            
            # Dapatkan chatroom ID
            chatroom_id = get_chatroom_id(session_id, processed_cookie)
            if chatroom_id:
                st.success(f"Chatroom ID: {chatroom_id}")
                
                # Aktifkan monitoring
                st.session_state.monitoring_params['monitoring_active'].set()
                
                # Jalankan thread
                thread = threading.Thread(
                    target=message_worker,
                    args=(chatroom_id,
                          st.session_state.monitoring_params['monitoring_active'],
                          st.session_state.monitoring_params['message_queue']),
                    daemon=True
                )
                thread.start()
                st.session_state.monitoring_params['monitoring_thread'] = thread
                st.info("Monitoring dimulai...")
            else:
                st.error("Gagal mendapatkan chatroom ID")
        else:
            st.error(live_check.get("status"))

# Proses antrian pesan di main thread
def process_messages():
    current_time = datetime.now()
    queue = st.session_state.monitoring_params['message_queue']
    
    while True:
        try:
            msg = queue.get_nowait()
            if msg['type'] == 'debug':
                st.session_state.monitoring_params['chat_messages'].insert(0, {
                    'timestamp': current_time.strftime("%H:%M:%S"),
                    'user': 'SYSTEM',
                    'message': msg['message']
                })
            elif msg['type'] == 'chat':
                # Filter duplikat dan waktu
                existing = [c for c in st.session_state.monitoring_params['last_comments']
                            if c['nickname'] == msg['nickname'] and 
                            c['content'] == msg['content'] and
                            (current_time - c['time']).total_seconds() < 5]
                
                if not existing:
                    st.session_state.monitoring_params['last_comments'].append(msg)
                    st.session_state.monitoring_params['chat_messages'].insert(0, {
                        'timestamp': msg['time'].strftime("%H:%M:%S"),
                        'user': msg['nickname'],
                        'message': msg['content']
                    })
            queue.task_done()
        except Empty:
            break

# Tampilkan pesan
if st.session_state.monitoring_params['chat_messages']:
    st.header("Live Chat Messages")
    st.write(f"Total Pesan: {len(st.session_state.monitoring_params['chat_messages'])}")
    st.table(st.session_state.monitoring_params['chat_messages'])
else:
    st.info("Belum ada pesan masuk")

# Tombol stop
if st.session_state.monitoring_params['monitoring_active'].is_set():
    if st.button("Stop Monitoring"):
        # Hentikan thread
        st.session_state.monitoring_params['monitoring_active'].clear()
        
        # Bersihkan antrian
        while not st.session_state.monitoring_params['message_queue'].empty():
            try:
                st.session_state.monitoring_params['message_queue'].get_nowait()
            except Empty:
                break
        
        # Reset data
        st.session_state.monitoring_params['chat_messages'] = []
        st.session_state.monitoring_params['last_comments'] = []
        st.experimental_rerun()

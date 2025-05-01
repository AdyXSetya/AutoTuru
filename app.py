import streamlit as st
import requests
from datetime import datetime
import json

# ===============================
# INISIALISASI SESSION STATE
# ===============================
if 'monitoring' not in st.session_state:
    st.session_state.monitoring = {
        'active': False,
        'chat_messages': [],
        'last_comments': [],
        'last_update': datetime.now(),
        'chatroom_id': None,
        'cookie': None,
    }

# ===============================
# FUNGSI UTILITAS
# ===============================
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

def check_live(cookie):
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"

    try:
        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X)",
            "Cookie": cookie
        })
        data = response.json()
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            live_info = data["data"]["list"][0]
            if live_info.get("status") == 1:
                return {
                    "status": "SEDANG LIVE",
                    "session_id": live_info.get("sessionId")
                }
        return {"status": "TIDAK LIVE"}
    except Exception as e:
        return {"status": f"Error: {str(e)}"}

def get_chatroom_id(session_id, cookie):
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}"
    try:
        response = requests.get(url, headers={
            "User-Agent": "Android app Shopee",
            "Cookie": cookie
        })
        return response.json().get('data', {}).get('session', {}).get('chatroom_id')
    except Exception as e:
        return None

def fetch_chat(chatroom_id):
    try:
        response = requests.get(
            f"https://chatroom-live.shopee.co.id/api/v1/fetch/chatroom/{chatroom_id}/message",
            headers={"User-Agent": "Android app Shopee"},
            timeout=10
        )
        return response.json().get('data', {}).get('messages', [])
    except Exception as e:
        st.error(f"Fetch error: {str(e)}")
        return []

# ===============================
# ANTARMUKA UTAMA
# ===============================
st.title("🔴 Shopee Live Chat Monitor (Manual Refresh)")

# Sidebar
status_box = st.sidebar.empty()
if st.session_state.monitoring['active']:
    status_box.success("Status: LIVE")
else:
    status_box.info("Status: Tidak Aktif")

# Input cookie
cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
if st.button("Mulai Monitoring"):
    if not cookie_input.strip():
        st.warning("Cookie tidak boleh kosong!")
    else:
        processed_cookie = cookie_sakti(cookie_input.strip())
        live_status = check_live(processed_cookie)

        if live_status.get("status") == "SEDANG LIVE":
            session_id = live_status.get("session_id")
            chatroom_id = get_chatroom_id(session_id, processed_cookie)

            if chatroom_id:
                st.session_state.monitoring.update({
                    'active': True,
                    'chatroom_id': chatroom_id,
                    'cookie': processed_cookie,
                    'chat_messages': [],
                    'last_comments': []
                })
                st.success(f"Monitoring dimulai untuk Chatroom ID: {chatroom_id}")
            else:
                st.error("Gagal mendapatkan Chatroom ID.")
        else:
            st.error("Tidak sedang live atau cookie salah.")

# ===============================
# TAMPILAN CHAT
# ===============================
st.header("💬 Live Chat Messages")

if st.session_state.monitoring['active']:
    if st.button("Refresh Chat"):
        chatroom_id = st.session_state.monitoring.get('chatroom_id')
        messages = fetch_chat(chatroom_id)

        new_msgs = []
        for msg in messages:
            nickname = msg.get('sender', {}).get('nickname', 'Unknown')
            content = msg.get('content', '')
            timestamp = datetime.now()

            # Decode JSON jika isi pesan nested
            if content.startswith('{'):
                try:
                    content = json.loads(content).get('content', '')
                except:
                    pass

            # Cek duplikat (5 detik batas waktu)
            is_duplicate = any(
                c['nickname'] == nickname and
                c['content'] == content and
                (timestamp - c['time']).total_seconds() < 5
                for c in st.session_state.monitoring['last_comments']
            )

            if not is_duplicate:
                st.session_state.monitoring['chat_messages'].insert(0, {
                    'timestamp': timestamp.strftime("%H:%M:%S"),
                    'nickname': nickname,
                    'content': content
                })
                st.session_state.monitoring['last_comments'].append({
                    'nickname': nickname,
                    'content': content,
                    'time': timestamp
                })

        # Batasi jumlah pesan
        st.session_state.monitoring['chat_messages'] = st.session_state.monitoring['chat_messages'][:200]

    # Tampilkan pesan
    messages = st.session_state.monitoring['chat_messages']
    if messages:
        for msg in messages:
            st.markdown(f"**[{msg['timestamp']}] {msg['nickname']}**: {msg['content']}")
    else:
        st.info("Belum ada pesan ditampilkan. Tekan 'Refresh Chat'.")

# Tombol stop
if st.session_state.monitoring['active']:
    if st.button("Stop Monitoring"):
        st.session_state.monitoring['active'] = False
        st.session_state.monitoring['chat_messages'] = []
        st.session_state.monitoring['last_comments'] = []
        st.success("Monitoring dihentikan.")

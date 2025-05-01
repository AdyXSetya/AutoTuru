import streamlit as st
import requests
from datetime import datetime

# Fungsi CookieSakti
def cookie_sakti(input_cookie):
    cookie_patch = 'SPC_F=fdecd079d2e0d109_unknown; SPC_AFTID=134e5e24-814c-420a-8d2b-332f0bcc7fc2'
    
    # Parsing cookie
    def parse_cookie(cookie_str):
        items = {}
        for part in cookie_str.split(';'):
            if '=' in part:
                key, value = part.split('=', 1)
                items[key.strip()] = value.strip()
        return items

    # Gabungkan cookie
    final_cookie = {}
    for key, value in parse_cookie(cookie_patch).items():
        final_cookie[key] = value
    for key, value in parse_cookie(input_cookie).items():
        final_cookie[key] = value

    # Format kembali ke string
    return '; '.join([f"{k}={v}" for k, v in final_cookie.items()])

# Fungsi Check_Live (diperbarui untuk menyimpan session_id)
def check_live(cookie):
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "Cookie": cookie
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            live_status = data["data"]["list"][0].get("status")
            session_id = data["data"]["list"][0].get("sessionId")
            
            if live_status == "1":
                return session_id, "SEDANG LIVE"
            else:
                return None, "TIDAK LIVE"
        else:
            return None, "Gagal mendapatkan data"
            
    except requests.exceptions.RequestException as e:
        return None, f"Error koneksi: {str(e)}"
    except (KeyError, IndexError, ValueError) as e:
        return None, f"Error parsing data: {str(e)}"

# Fungsi Check_Etalase
def check_etalase(session_id, cookie_sakti):
    url = f"https://live.shopee.co.id/api/v1/session/{session_id}/host/items?limit=100&offset=0"
    headers = {
        "User-Agent": "okhttp/3.12.4 app_type=1",
        "Cookie": cookie_sakti
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
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
    except requests.exceptions.RequestException as e:
        return f"Error koneksi: {str(e)}"
    except (KeyError, ValueError) as e:
        return f"Error parsing data: {str(e)}"

# UI Streamlit
st.title("Shopee Live & Etalase Checker")

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
check_live_btn = st.button("Cek Status Live")

if 'session_id' not in st.session_state:
    st.session_state.session_id = None

if check_live_btn and cookie_input:
    with st.spinner("Memproses..."):
        # Proses cookie sakti
        processed_cookie = cookie_sakti(cookie_input.strip())
        # Cek status live
        session_id, status = check_live(processed_cookie)
        st.session_state.session_id = session_id
        
        if session_id:
            st.success(f"Status: {status}")
            st.write(f"Session ID: `{session_id}`")
        else:
            st.error(f"Status: {status}")

# Bagian Etalase
if st.session_state.session_id:
    st.header("Cek Etalase")
    check_etalase_btn = st.button("Ambil Data Etalase")
    
    if check_etalase_btn:
        with st.spinner("Mengambil data etalase..."):
            # Proses cookie sakti lagi untuk kebutuhan API etalase
            processed_cookie = cookie_sakti(cookie_input.strip())
            etalase_data = check_etalase(st.session_state.session_id, processed_cookie)
            
            if isinstance(etalase_data, list):
                st.write(f"Total Produk: {len(etalase_data)}")
                st.dataframe(etalase_data)
            else:
                st.error("Gagal mendapatkan data etalase")

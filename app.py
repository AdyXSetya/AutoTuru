import streamlit as st
import requests
from datetime import datetime

def check_live(cookie):
    # Format tanggal YYYY-MM-DD
    now = datetime.now().strftime("%Y-%m-%d")
    url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "Cookie": cookie
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise error jika status != 200
        data = response.json()
        
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            live_status = data["data"]["list"][0].get("status")
            session_id = data["data"]["list"][0].get("sessionId")
            
            if live_status == 1:
                return session_id, "SEDANG LIVE"
            else:
                return None, "TIDAK LIVE"
        else:
            return None, "Gagal mendapatkan data"
            
    except requests.exceptions.RequestException as e:
        return None, f"Error koneksi: {str(e)}"
    except (KeyError, IndexError, ValueError) as e:
        return None, f"Error parsing data: {str(e)}"

# UI Streamlit
st.title("Cek Status Live Shopee")

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
check_button = st.button("Cek Status Live")

if check_button and cookie_input:
    with st.spinner("Memproses..."):
        session_id, status = check_live(cookie_input.strip())
        
    if session_id:
        st.success(f"Status: {status}")
        st.write(f"Session ID: `{session_id}`")
    else:
        st.error(f"Status: {status}")

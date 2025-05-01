import streamlit as st
import requests
from datetime import datetime

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

    # Parsing cookie
    patch_cookies = parse_cookie(cookie_patch)
    input_cookies = parse_cookie(input_cookie)
    
    # Gabungkan dengan prioritas patch terlebih dahulu
    final_cookie = {}
    # Tambahkan cookie dari input terlebih dahulu
    for key, value in input_cookies.items():
        final_cookie[key] = value
    # Timpa dengan cookie patch (agar patch punya prioritas lebih tinggi)
    for key, value in patch_cookies.items():
        final_cookie[key] = value

    # Format kembali ke string
    return '; '.join([f"{k}={v}" for k, v in final_cookie.items()])

# Fungsi Check Live + Etalase
def check_live_and_etalase(cookie):
    # Cek status live
    now = datetime.now().strftime("%Y-%m-%d")
    live_url = f"https://creator.shopee.co.id/supply/api/lm/sellercenter/liveList/v2?page=1&pageSize=1000&name=&orderBy=&sort=&timeDim=30d&endDate={now}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Beeshop locale=id version=33319 appver=33319 rnver=1725276035 shopee_rn_bundle_version=6028011 Shopee language=id app_type=1 platform=web_ios os_ver=17.6.1",
        "Cookie": cookie
    }
    
    try:
        # Request data live
        live_response = requests.get(live_url, headers=headers)
        live_data = live_response.json()
        
        if live_data.get("code") != 0 or not live_data.get("data", {}).get("list"):
            return {"status": "Gagal mendapatkan data live", "etalase": None}
            
        session_id = live_data["data"]["list"][0].get("sessionId")
        live_status = live_data["data"]["list"][0].get("status")
        
        if live_status != 1:
            return {"status": "TIDAK LIVE", "etalase": None}
            
        # Request data etalase
        etalase_url = f"https://live.shopee.co.id/api/v1/session/{session_id}/host/items?limit=100&offset=0"
        etalase_headers = {
            "User-Agent": "okhttp/3.12.4 app_type=1",
            "Cookie": cookie
        }
        
        etalase_response = requests.get(etalase_url, headers=etalase_headers)
        etalase_data = etalase_response.json()
        
        if etalase_data.get("err_code") != 0 or not etalase_data.get("data", {}).get("items"):
            return {"status": "SEDANG LIVE", "etalase": "Tidak ada data etalase"}
            
        items = []
        for idx, item in enumerate(etalase_data["data"]["items"], 1):
            items.append({
                "no": idx,
                "item_id": item.get("item_id"),
                "shop_id": item.get("shop_id"),
                "name": item.get("name", "").replace("|", "").replace("\n", "")
            })
            
        return {"status": "SEDANG LIVE", "etalase": items}
        
    except Exception as e:
        return {"status": f"Error: {str(e)}", "etalase": None}

# UI Streamlit
st.title("Shopee Live & Etalase Checker")

cookie_input = st.text_input("Masukkan Cookie Shopee Creator:")
process_btn = st.button("Cek Status & Ambil Data Etalase")

if process_btn and cookie_input:
    with st.spinner("Memproses..."):
        processed_cookie = cookie_sakti(cookie_input.strip())
        result = check_live_and_etalase(processed_cookie)
        
    # Tampilkan hasil
    if "status" in result:
        if result["status"] == "SEDANG LIVE":
            st.success("Status: SEDANG LIVE")
            if isinstance(result["etalase"], list):
                st.write(f"Total Produk: {len(result['etalase'])}")
                st.dataframe(result["etalase"])
            else:
                st.warning(result["etalase"])
        else:
            st.error(f"Status: {result['status']}")
else:
    st.info("Masukkan cookie dan klik tombol untuk memulai")

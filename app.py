import streamlit as st
from collections import deque

# Inisialisasi session state
if 'logs' not in st.session_state:
    st.session_state.logs = deque(maxlen=200)

# Tampilan Streamlit
st.title("Shopee Live Bot Monitor")
log_container = st.empty()

# Simulasi log
def simulate_logging():
    import time
    import threading
    for i in range(10):
        st.session_state.logs.append(f"Log entry {i}")
        time.sleep(1)

# Thread untuk simulasi
thread = threading.Thread(target=simulate_logging)
thread.start()

# Tampilkan log
while True:
    with log_container:
        st.text('\n'.join(st.session_state.logs))
    time.sleep(1)

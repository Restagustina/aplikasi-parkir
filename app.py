import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import qrcode
import tempfile
import os
import hashlib
import base64

# ---------------- FIREBASE SETUP ----------------
# Pastikan st.secrets['firebase'] sudah diatur
try:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            "storageBucket": "parkir-digital.appspot.com"
        })
    db = firestore.client()
    bucket = storage.bucket()
except Exception as e:
    st.error(f"Gagal menginisialisasi Firebase. Pastikan st.secrets['firebase'] sudah benar. Error: {e}")
    db = None
    bucket = None

# ---------------- HELPER FUNCTIONS (Diperlukan untuk Logika Login) ----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def log_activity(user_id, action):
    if db:
        db.collection("log_activity").add({
            "user_id": user_id,
            "action": action,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    else:
        print(f"Log activity: {action} for user {user_id}")

# ---------------- STREAMLIT APP ----------------
st.set_page_config(page_title="Digital ID Parkir Mahasiswa", page_icon="🅿️", layout="wide")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

# --------------------------------------------------------------------------
# --- FUNGSI & PANGGILAN BACKGROUND IMAGE (WAJIB DI AWAL SCRIPT) ---
# --------------------------------------------------------------------------

# Fungsi untuk mengkodekan gambar lokal ke Base64
def get_base64(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_background(image_file):
    try:
        bin_str = get_base64(image_file)
        page_bg_img = f'''
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/png;base64,{bin_str}");
            background-size: cover;
            background-repeat: no-repeat;
            background-attachment: fixed;
            position: relative;
        }}

        /* Overlay buram */
        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            bottom: 0;
            left: 0;
            background: rgba(0, 0, 0, 0.5); /* Layer transparan */
            backdrop-filter: blur(8px);           /* Efek buram */
            z-index: 0;
        }}

        /* Pastikan konten di atas overlay */
        [data-testid="stAppViewContainer"] > * {{
            position: relative;
            z-index: 1;
        }}

        [data-testid="stHeader"] {{
            background-color: rgba(0,0,0,0);
        }}
        </style>
        '''
        st.markdown(page_bg_img, unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"PERINGATAN: File gambar '{image_file}' tidak ditemukan. Latar belakang tidak diterapkan.")

# PANGGIL FUNGSI LATAR BELAKANG DI SINI
# Ganti 'BG FASILKOM.png' jika format atau namanya berbeda
set_background('BG FASILKOM.jpg')

# ---------------- LOGIN PAGE ----------------
# ---------------- LOGIN PAGE ----------------
if st.session_state.page == "login" and st.session_state.user is None:
    st.markdown("""
    <style>
    /* 1. CSS untuk menengahkan kontainer utama Streamlit */
    [data-testid="stAppViewContainer"] > .main {
        display: flex;
        justify-content: center; /* Horizontally center */
        align-items: center; /* Vertically center */
        padding: 0 !important; 
        min-height: 100vh;
    }

    /* 2. Style untuk Kotak Login */
    /* Kita menargetkan container yang dibuat oleh st.form (stForm) */
    [data-testid="stForm"] {
        background-color: rgba(255, 255, 255, 0.95); /* Kotak putih di tengah */
        padding: 30px;
        border-radius: 15px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3); 
        max-width: 450px; /* Lebar Kotak Login */
        width: 100%; 
        margin: auto;
    }
    
    /* 3. Perbaikan Input: Input dan tombol di dalam form harus mengisi 100% dari box */
    [data-testid="stForm"] div[data-testid="stTextInput"],
    [data-testid="stForm"] div[data-testid="stTextInput"] > div {
        max-width: 100%; 
        width: 100%;
    }
    
    /* Styling Tombol di dalam Form (Form hanya memiliki satu tombol, tombol Submit) */
    [data-testid="stForm"] div.stButton > button { 
        width: 100%;
        margin-top: 15px;
    }

    /* Judul di dalam box */
    [data-testid="stForm"] h3 {
        text-align: left;
        margin-bottom: 20px;
        color: #333;
    }

    /* Streamlit input custom style */
    div[data-testid="stTextInput"] > div > div > input {
        border-radius: 8px;
        border: 1px solid #ccc;
    }
    
    /* Tombol Daftar Akun Baru (SEKARANG DI LUAR FORM) */
    /* Kita menargetkan tombol 'Daftar' yang diletakkan persis di bawah form */
    div.stButton:last-of-type > button { 
        background-color:#ff4b4b; 
        color:white; 
        border-radius:10px; 
        border:none; 
        width: 100%; 
        max-width: 450px; /* Batasi lebarnya sama dengan form */
        margin-top: 10px;
    }

    .main .block-container {
        padding-top: 0;
    }
    
    </style>
    """, unsafe_allow_html=True)
    
    # st.empty() ditempatkan di luar form untuk memastikan centering bekerja sempurna
    st.empty() 
    
    # --- FORM (KOTAK LOGIN TUNGGAL) ---
with st.form("login_form", clear_on_submit=False):
        st.markdown("### 🔑 Login Pengguna") 

        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        # Tombol Login (ini adalah tombol submit form)
        submitted = st.form_submit_button("Login")

        # Logika Login HANYA berjalan ketika tombol submit form diklik (termasuk menekan ENTER)
        if submitted:
            if db:
                users = db.collection("users").where("email", "==", email).stream()
                user_found = False
                for u in users:
                    u_data = u.to_dict()
                    if u_data.get("password_hash") == hash_password(password):
                        st.session_state.user = {"uid": u.id, **u_data}
                        log_activity(u.id, "login")
                        st.success(f"Selamat datang, {u_data.get('nama')}!")
                        user_found = True
                        st.experimental_rerun() # <<< TAMBAH BARIS INI
                        break
                if not user_found:
                    st.error("Email atau password salah!")
            else:
                st.error("Koneksi ke database gagal.")

    # Tombol Daftar Akun Baru (Diletakkan di luar form, tapi tepat di bawahnya)
    if st.button("Daftar Akun Baru", key="goto_register"):
        st.session_state.page = "register"
        st.experimental_rerun() # <<< TAMBAH BARIS INI UNTUK PERPINDAHAN PAGE

    st.empty()

# ---------------- REGISTER PAGE ----------------
elif st.session_state.page == "register" and st.session_state.user is None:
    st.subheader("📝 Form Registrasi User Baru")
    reg_nama = st.text_input("Nama Lengkap", key="reg_nama")
    reg_nim = st.text_input("NIM", key="reg_nim")
    reg_email = st.text_input("Email", key="reg_email")
    reg_password = st.text_input("Password", type="password", key="reg_password")
    reg_password2 = st.text_input("Konfirmasi Password", type="password", key="reg_password2")

    if st.button("Daftar Sekarang", key="btn_register"):
        if reg_password != reg_password2:
            st.error("Password dan konfirmasi tidak sama!")
        elif reg_nama and reg_nim and reg_email and reg_password:
            uid = register_user(reg_nama, reg_nim, reg_email, reg_password)
            if uid:
                st.success("Akun berhasil dibuat! Silahkan login.")
                st.session_state.page = "login"
            else:
                st.error("Email sudah terdaftar!")
        else:
            st.error("Lengkapi semua data!")

    if st.button("Kembali ke Login", key="back_login"):
        st.session_state.page = "login"

# ---------------- APP UTAMA ----------------
elif st.session_state.user:
    st.sidebar.title("Menu")
    menu = st.sidebar.selectbox("", ["Profil", "Daftar Kendaraan", "Lihat Data Kendaraan"])
    if st.sidebar.button("Logout"):
        log_activity(st.session_state.user['uid'], "logout")
        st.session_state.user = None
        st.session_state.page = "login"
        st.experimental_rerun()

    user_id = st.session_state.user['uid']
    st.success(f"Selamat datang, {st.session_state.user['nama']}!")

    # ---------- PROFIL ----------
    if menu == "Profil":
        st.header("Profil Pengguna")
        st.write(f"Nama: {st.session_state.user['nama']}")
        st.write(f"NIM: {st.session_state.user['nim']}")
        st.write(f"Email: {st.session_state.user['email']}")

        st.subheader("Log Aktivitas")
        logs = get_user_logs(user_id)
        if logs:
            for l in logs:
                ts = l['timestamp'].strftime("%d-%m-%Y %H:%M:%S") if l['timestamp'] else "-"
                st.write(f"{l['action'].capitalize()} → {ts}")
        else:
            st.info("Belum ada aktivitas login/logout.")

    # ---------- DAFTAR KENDARAAN ----------
    elif menu == "Daftar Kendaraan":
        st.header("Form Pendaftaran Kendaraan")
        nama = st.text_input("Nama Lengkap", value=st.session_state.user['nama'])
        nim = st.text_input("NIM", value=st.session_state.user['nim'])
        plat = st.text_input("Plat Nomor")
        jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
        foto = st.file_uploader("Upload Foto Kendaraan", type=["jpg","jpeg","png"])

        if st.button("Daftar Kendaraan"):
            if nama and nim and plat and jenis and foto:
                tmp_foto = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                tmp_foto.write(foto.getbuffer())
                tmp_foto.close()
                foto_url = upload_to_storage(tmp_foto.name, f"foto/{plat}.png")

                qr_data = f"{nama}-{nim}-{plat}"
                qr_filename = f"qr_{plat}.png"
                img = qrcode.make(qr_data)
                img.save(qr_filename)
                qr_url = upload_to_storage(qr_filename, f"qr/{qr_filename}")

                save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url)

                st.success("✅ Data kendaraan berhasil disimpan!")
                st.image(qr_filename, caption="QR Code Parkir Anda")

                os.remove(tmp_foto.name)
                os.remove(qr_filename)
            else:
                st.error("⚠️ Lengkapi semua data dan upload foto kendaraan.")

    # ---------- LIHAT DATA KENDARAAN ----------
    elif menu == "Lihat Data Kendaraan":
        st.header("Data Kendaraan Saya")
        data = get_user_vehicles(user_id)
        if data:
            for d in data:
                st.subheader(f"{d['nama']} ({d['nim']})")
                st.write(f"Plat: {d['plat']} | Jenis: {d['jenis']}")
                st.image(d["foto_url"], caption="Foto Kendaraan", width=200)
                st.image(d["qr_url"], caption="QR Code", width=150)
                st.markdown("---")
        else:
            st.info("Belum ada data kendaraan yang terdaftar.")

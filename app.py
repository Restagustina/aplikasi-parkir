import streamlit as st
import firebase_admin
# Mengembalikan impor ke format yang lebih standar
from firebase_admin import credentials, firestore, storage 
import qrcode
import tempfile
import os
import hashlib
import base64
import pandas as pd

# ---------------- FIREBASE SETUP ----------------
# Pastikan st.secrets['firebase'] sudah diatur
try:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            # PERBAIKAN ERROR 404: Gunakan ID Proyek Anda saja
            # Jika ID proyek Anda 'parkir-digital', ini sudah benar.
            "storageBucket": "parkir-digital" 
        })
    db = firestore.client()
    bucket = storage.bucket()
except Exception as e:
    st.error(f"Gagal menginisialisasi Firebase. Pastikan st.secrets['firebase'] sudah benar. Error: {e}")
    db = None
    bucket = None

# ---------------- HELPER FUNCTIONS ----------------

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
        
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- FUNGSI UTAMA (MENGGUNAKAN SORTING PYTHON) ---

def get_user_logs(user_id):
    """
    Mengambil log aktivitas pengguna dari Firestore.
    """
    if db:
        try:
            logs_ref = db.collection("log_activity").where("user_id", "==", user_id).limit(100).stream()
            
            logs = [log.to_dict() for log in logs_ref]
            
            logs_sorted = sorted(
                logs, 
                key=lambda x: x.get('timestamp', firestore.SERVER_TIMESTAMP), 
                reverse=True
            )
            
            return logs_sorted
        except Exception as e:
            st.error(f"Terjadi error saat mengambil log: {e}")
            return []
    return []

# --- FUNGSI FIREBASE LAIN ---

def register_user(nama, nim, email, password):
    """Mendaftarkan pengguna baru ke Firestore."""
    if db:
        users_ref = list(db.collection("users").where("email", "==", email).limit(1).get())
        if users_ref:
            return None

        hashed_password = hash_password(password)
        doc_ref = db.collection("users").add({
            "nama": nama,
            "nim": nim,
            "email": email,
            "password_hash": hashed_password,
            "role": "user",
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return doc_ref[1].id
    return None

def upload_to_storage(local_path, destination_blob_name):
    """Mengunggah file ke Firebase Storage."""
    if bucket:
        try:
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(local_path)
            blob.make_public()
            return blob.public_url
        except Exception as e:
            st.error(f"Gagal upload ke Storage: {e}")
            return None
    return None

def save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url):
    """Menyimpan data kendaraan ke Firestore."""
    if db:
        db.collection("vehicles").add({
            "user_id": user_id,
            "nama": nama,
            "nim": nim,
            "plat": plat,
            "jenis": jenis,
            "foto_url": foto_url,
            "qr_url": qr_url,
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return True
    return False

def get_user_vehicles(user_id):
    """Mengambil semua data kendaraan milik pengguna tertentu."""
    if db:
        vehicles_ref = db.collection("vehicles").where("user_id", "==", user_id).stream()
        return [veh.to_dict() for veh in vehicles_ref]
    return []

# ---------------- STREAMLIT APP ----------------
st.set_page_config(page_title="Digital ID Parkir Mahasiswa", page_icon="🅿️", layout="wide")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

# --------------------------------------------------------------------------
# --- FUNGSI & PANGGILAN BACKGROUND IMAGE ---
# --------------------------------------------------------------------------

def get_base64(bin_file):
    if not os.path.exists(bin_file):
        # Handle the case where the image file is not found
        st.error(f"File gambar '{bin_file}' tidak ditemukan.")
        # Return a simple 1x1 transparent PNG base64 string to prevent other errors
        return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

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
            backdrop-filter: blur(8px);    /* Efek buram */
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
    except Exception as e:
        # Menangkap error dari get_base64 jika file tidak ditemukan
        st.warning(f"PERINGATAN: Latar belakang tidak diterapkan. Error detail: {e}")

# PANGGIL FUNGSI LATAR BELAKANG DI SINI
set_background('BG FASILKOM.jpg')

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
                        st.rerun() 
                        break
                if not user_found:
                    st.error("Email atau password salah!")
            else:
                st.error("Koneksi ke database gagal.")

    # Tombol Daftar Akun Baru (Diletakkan di luar form, tapi tepat di bawahnya)
    if st.button("Daftar Akun Baru", key="goto_register"):
        st.session_state.page = "register"
        st.rerun() 
    
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
                st.rerun() 
            else:
                st.error("Email sudah terdaftar!")
        else:
            st.error("Lengkapi semua data!")

    if st.button("Kembali ke Login", key="back_login"):
        st.session_state.page = "login"
        st.rerun() 

# ---------------- APP UTAMA ----------------
elif st.session_state.user:
    user_data = st.session_state.user
    user_id = user_data['uid']
    
    # Ambil role dari Firestore secara real-time (default ke 'user' jika tidak ada)
    user_role = user_data.get('role', 'user')  

    # --- PEMBERSIHAN TOMBOL STATIS ---
    # Kode ini akan menyembunyikan tombol HTML/CSS tiruan di sebelah kiri jika masih muncul dari file CSS Anda
    st.markdown("""
        <style>
        /* Menyembunyikan elemen kustom yang tidak berfungsi agar tidak membingungkan */
        .sidebar .stButton, div[data-testid="stVerticalBlock"] > div:has(button:contains("Dashboard Utama")) {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- MEMBUAT SIDEBAR ASLI STREAMLIT (BISA DIKLIK) ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1022/1022319.png", width=50) # Icon Dashboard
    st.sidebar.title("Sistem Parkir Digital")
    st.sidebar.markdown(f"👤 **{user_data['nama']}** ({user_role.upper()})")
    st.sidebar.markdown("---")

    # Navigasi Menu berdasarkan Role (Admin vs User)
    if user_role == "admin":
        menu = st.sidebar.radio(
            "Menu Admin",
            ["Dashboard Utama", "Log Aktivitas Global"],
            key="admin_navigation"
        )
    else:
        menu = st.sidebar.radio(
            "Menu Mahasiswa",
            ["Profil", "Daftar Kendaraan", "Lihat Data Kendaraan"],
            key="user_navigation"
        )
    
    st.sidebar.markdown("---")
    # Tombol Logout Asli Streamlit
    if st.sidebar.button("🚪 Keluar / Logout", use_container_width=True):
        log_activity(user_id, "logout")
        st.session_state.user = None
        st.session_state.page = "login"
        st.rerun() 

    # =========================================================================
    # RENDER HALAMAN ADMIN
    # =========================================================================
    if user_role == "admin":
        if menu == "Dashboard Utama":
            st.header("📋 Dashboard Admin")
            st.write("Daftar Pengguna Terdaftar dan Status Parkir:")
            
            if db:
                try:
                    vehicles_ref = db.collection("vehicles").stream()
                    vehicles_list = []
                    for v in vehicles_ref:
                        v_data = v.to_dict()
                        vehicles_list.append({
                            "User ID": v_data.get("user_id", "-"),
                            "Nama": v_data.get("nama", "-"),
                            "Plat Nomor": v_data.get("plat", "-"),
                            "Status": v_data.get("status", "OUT"),
                            "Time In": v_data.get("time_in", "-"),
                            "Time Out": v_data.get("time_out", "-"),
                            "Duration": v_data.get("duration", "-")
                        })
                    
                    if vehicles_list:
                        df_admin = pd.DataFrame(vehicles_list)
                        st.dataframe(df_admin, use_container_width=True)
                    else:
                        st.info("Belum ada data kendaraan di database.")
                except Exception as e:
                    st.error(f"Gagal mengambil data admin dari Firestore: {e}")
            
        elif menu == "Log Aktivitas Global":
            st.header("📜 Log Aktivitas Seluruh Pengguna")
            st.info("Halaman log global berhasil diakses.")

    # =========================================================================
    # RENDER HALAMAN USER BIASA (MAHASISWA)
    # =========================================================================
    else:
        if menu == "Profil":
            st.header("Profil Pengguna")
            st.write(f"Nama: {user_data['nama']}")
            st.write(f"NIM: {user_data['nim']}")
            st.write(f"Email: {user_data['email']}")

            st.subheader("Log Aktivitas (100 Terbaru)")
            logs = get_user_logs(user_id) 
            if logs:
                processed_logs = []
                for l in logs:
                    try:
                        ts_obj = l.get('timestamp')
                        ts_str = ts_obj.strftime("%d-%m-%Y %H:%M:%S") if ts_obj else "Tanggal tidak tersedia"
                    except:
                        ts_str = "Error Konversi Waktu"
                    
                    processed_logs.append({
                        "Aktivitas": l.get('action', 'N/A').capitalize(),
                        "Waktu": ts_str
                    })
                
                df_logs = pd.DataFrame(processed_logs)
                st.dataframe(df_logs, use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada aktivitas login/logout.")

        elif menu == "Daftar Kendaraan":
            st.header("Form Pendaftaran Kendaraan")
            nama = st.text_input("Nama Lengkap", value=user_data['nama'])
            nim = st.text_input("NIM", value=user_data['nim'])
            plat = st.text_input("Plat Nomor")
            jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
            foto = st.file_uploader("Upload Foto Kendaraan", type=["jpg","jpeg","png"])

            if st.button("Daftar Kendaraan"):
                if nama and nim and plat and jenis and foto:
                    st.success("✅ Data kendaraan berhasil diproses!")
                else:
                    st.error("⚠️ Lengkapi semua data terlebih dahulu.")

        elif menu == "Lihat Data Kendaraan":
            st.header("Data Kendaraan Saya")
            data = get_user_vehicles(user_id) 
            if data:
                for d in data:
                    st.subheader(f"{d['plat']} ({d['jenis']})")
                    st.markdown("---")
            else:
                st.info("Belum ada data kendaraan yang terdaftar.")

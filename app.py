import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import qrcode
import tempfile
import os
import hashlib
import base64

# ---------------- FIREBASE SETUP ----------------
cred = credentials.Certificate(dict(st.secrets["firebase"]))
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "storageBucket": "parkir-digital.appspot.com"
    })

db = firestore.client()
bucket = storage.bucket()

# ---------------- HELPER FUNCTIONS ----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(nama, nim, email, password):
    user_doc = db.collection("users").where("email", "==", email).stream()
    for u in user_doc:
        return None
    new_user = {
        "nama": nama,
        "nim": nim,
        "email": email,
        "password_hash": hash_password(password)
    }
    user_ref = db.collection("users").add(new_user)
    return user_ref[1].id

def log_activity(user_id, action):
    db.collection("log_activity").add({
        "user_id": user_id,
        "action": action,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

# def get_user_logs(user_id):
#     docs = db.collection("log_activity").where("user_id", "==", user_id)\
#         .order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
#     return [d.to_dict() for d in docs]
def get_user_logs(user_id):
    docs = db.collection("log_activity").where("user_id", "==", user_id).stream()
    logs = [d.to_dict() for d in docs]
    # Sort manual berdasarkan timestamp descending
    logs_sorted = sorted(logs, key=lambda x: x['timestamp'] or 0, reverse=True)
    return logs_sorted
    

def save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url):
    data = {
        "user_id": user_id,
        "nama": nama,
        "nim": nim,
        "plat": plat,
        "jenis": jenis,
        "foto_url": foto_url,
        "qr_url": qr_url,
        "created_at": firestore.SERVER_TIMESTAMP
    }
    db.collection("kendaraan").add(data)

def upload_to_storage(file_path, filename):
    blob = bucket.blob(filename)
    blob.upload_from_filename(file_path)
    blob.make_public()
    return blob.public_url

def get_user_vehicles(user_id):
    docs = db.collection("kendaraan").where("user_id", "==", user_id).stream()
    return [d.to_dict() for d in docs]

# ---------------- STREAMLIT APP ----------------
st.set_page_config(page_title="Digital ID Parkir Mahasiswa", page_icon="🅿️", layout="wide")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"  # login atau register

# --- Fungsi untuk Background Image ---
def get_base64(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_background(image_file):
    bin_str = get_base64(image_file)
    page_bg_img = f'''
    <style>
    .stApp {{
        background-image: url("data:image/png;base64,{bin_str}");
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    /* Menghapus header Streamlit bawaan (opsional, agar gambar full) */
    .stApp > header {{
        background-color: rgba(0,0,0,0); 
    }}
    </style>
    '''
    st.markdown(page_bg_img, unsafe_allow_html=True)

# ---------------- LOGIN PAGE ----------------
if st.session_state.page == "login" and st.session_state.user is None:
    st.markdown("""
    <style>
    /* CSS untuk background sudah dipindahkan ke fungsi set_background */

    /* Container untuk menengahkan login box di tengah halaman */
    .center-container {
        display: flex;
        justify-content: center; /* Horizontally center */
        align-items: center; /* Vertically center */
        height: 100vh; /* Tinggi penuh viewport */
        width: 100vw;
        position: fixed; /* Tetapkan posisi agar tidak terpengaruh konten lain */
        top: 0;
        left: 0;
        z-index: 9999; /* Pastikan di atas konten lain */
    }
    
    .login-box {
        background-color: rgba(255, 255, 255, 0.9); /* Ubah ke putih transparan agar background terlihat */
        padding: 30px;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        max-width: 400px; /* Batasi lebar box */
        width: 90%; /* Agar responsif */
    }
    
    .btn-register {
        background-color:#ff4b4b; 
        color:white; 
        padding:10px 20px; 
        border-radius:10px; 
        border:none; 
        cursor:pointer;
        width: 100%; /* Agar tombol selebar login box */
        margin-top: 10px; /* Jarak dari tombol login */
    }

    /* CSS tambahan untuk meratakan tombol Daftar Akun Baru */
    div.stButton > button:last-child {
        width: 100%;
        margin-top: 10px;
    }

    /* Streamlit input custom style (Opsional: agar input terlihat lebih baik di box) */
    div[data-testid="stTextInput"] > div > div > input {
        border-radius: 8px;
        border: 1px solid #ccc;
    }
    
    </style>
    """, unsafe_allow_html=True)

    # Wrap login box dengan center-container
    st.markdown('<div class="center-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    
    st.subheader("🔑 Login Pengguna")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login", key="btn_login"):
        users = db.collection("users").where("email", "==", email).stream()
        user_found = False
        for u in users:
            u_data = u.to_dict()
            if u_data["password_hash"] == hash_password(password):
                st.session_state.user = {"uid": u.id, **u_data}
                log_activity(u.id, "login")
                st.success(f"Selamat datang, {u_data['nama']}!")
                user_found = True
                break
        if not user_found:
            st.error("Email atau password salah!")

    # Tombol daftar merah
    # Kita tidak bisa menerapkan .btn-register langsung ke st.button,
    # jadi kita gunakan CSS selector untuk st.button terakhir (karena tombol Login sudah yang pertama)
    if st.button("Daftar Akun Baru", key="goto_register"):
        st.session_state.page = "register"
    
    st.markdown('</div>', unsafe_allow_html=True) # Tutup login-box
    st.markdown('</div>', unsafe_allow_html=True) # Tutup center-container

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

import streamlit as st
import firebase_admin
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
            "storageBucket": "parkir-digital.appspot.com"
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

# --- FUNGSI QR CODE BARU ---
def generate_and_store_qr(user_id, nim):
    """
    Membuat QR Code dengan data User ID, mengupload ke Storage,
    dan menyimpan URL-nya di dokumen pengguna.
    """
    if not bucket or not db:
        st.error("Koneksi Firebase gagal, QR Code tidak dapat dibuat.")
        return None
        
    # 1. Tentukan Data QR (gunakan User ID)
    qr_data = f"USER_ID:{user_id}" 
    filename = f"qr_user_{nim}.png"
    tmp_dir = tempfile.gettempdir()
    qr_path = os.path.join(tmp_dir, filename)

    try:
        # 2. Generate dan Simpan QR Code di lokal temp
        img = qrcode.make(qr_data)
        img.save(qr_path)
        
        # 3. Upload ke Firebase Storage
        qr_url = upload_to_storage(qr_path, f"qr_identitas/{filename}")
        
        if qr_url:
            # 4. Simpan URL QR di dokumen user Firestore
            user_ref = db.collection("users").document(user_id)
            user_ref.update({"qr_identitas_url": qr_url})
            
            # 5. Update session state (agar tampilan diperbarui)
            st.session_state.user['qr_identitas_url'] = qr_url
            
            return qr_url
        else:
            return None
    except Exception as e:
        st.error(f"Gagal memproses QR Code: {e}")
        return None
    finally:
        # Bersihkan file temp lokal
        if os.path.exists(qr_path):
            os.remove(qr_path)


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
# ... (FUNGSI upload_to_storage, save_data_firestore, get_user_vehicles, register_user tetap sama)

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
            "created_at": firestore.SERVER_TIMESTAMP,
            "qr_identitas_url": "" # Tambahkan field kosong untuk QR
        })
        return doc_ref[1].id
    return None

def upload_to_storage(local_path, destination_blob_name):
    # ... (Fungsi ini tetap sama)
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
    # ... (Fungsi ini tetap sama)
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
    # ... (Fungsi ini tetap sama)
    """Mengambil semua data kendaraan milik pengguna tertentu."""
    if db:
        vehicles_ref = db.collection("vehicles").where("user_id", "==", user_id).stream()
        return [veh.to_dict() for veh in vehicles_ref]
    return []


# ---------------- STREAMLIT APP ----------------
st.set_page_config(page_title="Digital ID Parkir Mahasiswa", page_icon="🅿️", layout="wide")

# Session state
# ... (Session state tetap sama)
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

# --------------------------------------------------------------------------
# --- FUNGSI & PANGGILAN BACKGROUND IMAGE ---
# ... (Fungsi background image tetap sama)
def get_base64(bin_file):
    if not os.path.exists(bin_file):
        st.error(f"File gambar '{bin_file}' tidak ditemukan.")
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

        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            bottom: 0;
            left: 0;
            background: rgba(0, 0, 0, 0.5); 
            backdrop-filter: blur(8px);    
            z-index: 0;
        }}

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
        st.warning(f"PERINGATAN: Latar belakang tidak diterapkan. Error detail: {e}")

# PANGGIL FUNGSI LATAR BELAKANG DI SINI
set_background('BG FASILKOM.jpg')

# ---------------- LOGIN PAGE & REGISTER PAGE (Tetap Sama) ----------------
# ... (Blok kode LOGIN PAGE dan REGISTER PAGE tetap sama)

if st.session_state.page == "login" and st.session_state.user is None:
    # ... (Login form and logic)
    st.markdown("""
    <style>
    /* ... (CSS tetap sama) ... */
    [data-testid="stAppViewContainer"] > .main {
        display: flex;
        justify-content: center; /* Horizontally center */
        align-items: center; /* Vertically center */
        padding: 0 !important; 
        min-height: 100vh;
    }
    [data-testid="stForm"] {
        background-color: rgba(255, 255, 255, 0.95); 
        padding: 30px;
        border-radius: 15px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3); 
        max-width: 450px; 
        width: 100%; 
        margin: auto;
    }
    div.stButton:last-of-type > button { 
        background-color:#ff4b4b; 
        color:white; 
        border-radius:10px; 
        border:none; 
        width: 100%; 
        max-width: 450px; 
        margin-top: 10px;
    }
    .main .block-container {
        padding-top: 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.empty() 
    
    with st.form("login_form", clear_on_submit=False):
        st.markdown("### 🔑 Login Pengguna") 

        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        submitted = st.form_submit_button("Login")

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

    if st.button("Daftar Akun Baru", key="goto_register"):
        st.session_state.page = "register"
        st.rerun() 
    
    st.empty()

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
    st.sidebar.title("Menu")
    menu = st.sidebar.selectbox("", ["Profil", "Tampilkan QR Code", "Daftar Kendaraan", "Lihat Data Kendaraan"])
    
    if st.sidebar.button("Logout"):
        log_activity(st.session_state.user['uid'], "logout")
        st.session_state.user = None
        st.session_state.page = "login"
        st.rerun() 

    user_id = st.session_state.user['uid']
    st.success(f"Selamat datang, {st.session_state.user['nama']}!")

    # ---------- PROFIL ----------
    if menu == "Profil":
        st.header("Profil Pengguna")
        st.write(f"Nama: {st.session_state.user['nama']}")
        st.write(f"NIM: {st.session_state.user['nim']}")
        st.write(f"Email: {st.session_state.user['email']}")
        
        # LOG AKTIVITAS (Menggunakan try-except untuk mengatasi Error Timestamp)
        st.subheader("Log Aktivitas (100 Terbaru)")
        logs = get_user_logs(user_id) 
        
        if logs:
            processed_logs = []
            for l in logs:
                try:
                    ts_obj = l.get('timestamp')
                    if ts_obj:
                        ts_str = ts_obj.strftime("%d-%m-%Y %H:%M:%S")
                    else:
                        ts_str = "Tanggal tidak tersedia"
                except AttributeError:
                    ts_str = "Error Konversi Waktu"
                except Exception:
                    ts_str = "Data Waktu Rusak"
                
                processed_logs.append({
                    "Aktivitas": l.get('action', 'N/A').capitalize(),
                    "Waktu": ts_str
                })
            
            df_logs = pd.DataFrame(processed_logs)
            
            st.dataframe(df_logs, use_container_width=True, hide_index=True)
            
            csv_data = convert_df_to_csv(df_logs)
            
            st.download_button(
                label="📥 Download Data Log (CSV)",
                data=csv_data,
                file_name=f'log_aktivitas_{st.session_state.user["nim"]}.csv',
                mime='text/csv',
                use_container_width=True
            )
            
        else:
            st.info("Belum ada aktivitas login/logout.")

    # ---------- TAMPILKAN QR CODE BARU ----------
    elif menu == "Tampilkan QR Code":
        st.header("Digital Identity QR Code")
        qr_url = st.session_state.user.get('qr_identitas_url')

        if qr_url and qr_url != "":
            st.info("Ini adalah ID digital Anda. Silakan tunjukkan ini saat pemeriksaan.")
            st.image(qr_url, caption="QR Code Identitas Parkir", width=300)
            
            # Tambahkan tombol untuk download gambar QR
            st.markdown(f'<a href="{qr_url}" download="qr_identitas_{st.session_state.user["nim"]}.png" target="_blank"><button style="background-color: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Download QR Code</button></a>', unsafe_allow_html=True)
            
        else:
            st.warning("Anda belum memiliki QR Code Identitas. Silakan buat QR Code.")
            
            # Tombol untuk generate QR Code
            if st.button("Generate QR Code Sekarang"):
                with st.spinner('Membuat dan menyimpan QR Code...'):
                    new_qr_url = generate_and_store_qr(
                        user_id=st.session_state.user['uid'],
                        nim=st.session_state.user['nim']
                    )
                
                if new_qr_url:
                    st.success("QR Code berhasil dibuat dan disimpan!")
                    # Memaksa rerun untuk menampilkan QR Code
                    st.rerun() 
                else:
                    st.error("Gagal membuat QR Code.")


    # ---------- DAFTAR KENDARAAN ----------
    elif menu == "Daftar Kendaraan":
        # ... (Blok kode DAFTAR KENDARAAN tetap sama)
        st.header("Form Pendaftaran Kendaraan")
        nama = st.text_input("Nama Lengkap", value=st.session_state.user['nama'])
        nim = st.text_input("NIM", value=st.session_state.user['nim'])
        plat = st.text_input("Plat Nomor")
        jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
        foto = st.file_uploader("Upload Foto Kendaraan", type=["jpg","jpeg","png"])

        if st.button("Daftar Kendaraan"):
            if nama and nim and plat and jenis and foto:
                tmp_dir = tempfile.gettempdir()
                tmp_foto_path = os.path.join(tmp_dir, f"{plat}_foto.png")
                with open(tmp_foto_path, "wb") as f:
                    f.write(foto.getbuffer())
                
                foto_url = upload_to_storage(tmp_foto_path, f"foto/{plat}.png")

                qr_data = f"{nama}-{nim}-{plat}"
                qr_filename = os.path.join(tmp_dir, f"qr_{plat}.png")
                img = qrcode.make(qr_data)
                img.save(qr_filename)
                qr_url = upload_to_storage(qr_filename, f"qr/{qr_filename}")

                if foto_url and qr_url:
                    save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url)
                    st.success("✅ Data kendaraan berhasil disimpan!")
                    st.image(qr_filename, caption="QR Code Parkir Anda")
                else:
                    st.error("Gagal mengupload file ke Storage!")

                if os.path.exists(tmp_foto_path):
                    os.remove(tmp_foto_path)
                if os.path.exists(qr_filename):
                    os.remove(qr_filename)
            else:
                st.error("⚠️ Lengkapi semua data dan upload foto kendaraan.")


    # ---------- LIHAT DATA KENDARAAN ----------
    elif menu == "Lihat Data Kendaraan":
        # ... (Blok kode LIHAT DATA KENDARAAN tetap sama)
        st.header("Data Kendaraan Saya")
        data = get_user_vehicles(user_id) 
        if data:
            for d in data:
                st.subheader(f"{d['plat']} ({d['jenis']})")
                st.write(f"Pemilik: {d['nama']} ({d['nim']})")
                st.image(d["foto_url"], caption="Foto Kendaraan", width=200)
                st.image(d["qr_url"], caption="QR Code", width=150)
                st.markdown("---")
        else:
            st.info("Belum ada data kendaraan yang terdaftar.")

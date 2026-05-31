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
    user_role = user_data.get('role', 'user')  # Mengambil role: admin / user
    
    # --- INISIALISASI VARIABEL MONITOR (DARI KODE PERTAMA) ---
    if 'monitor_html' not in st.session_state:
        st.session_state.monitor_html = "<div style='background-color: #f1f3f5; color: #495057; padding: 20px; border-radius: 5px; text-align: center; height: 50vh; display: flex; flex-direction: column; justify-content: center;'><h1 style='font-size: 50px;'>🅿️ MONITOR GATE READY</h1><p style='font-size: 20px;'>Silakan lakukan scan QR Code pada kamera di bawah.</p></div>"
    if 'monitor_display_time' not in st.session_state:
        st.session_state.monitor_display_time = datetime.now() - timedelta(seconds=6)
    if 'monitor_type' not in st.session_state:
        st.session_state.monitor_type = 'default'

    # --- SIDEBAR MENU (PILIHAN NAVIGATION) ---
    st.sidebar.title("🅿️ Parkir Digital")
    st.sidebar.markdown(f"Login Sebagai: **{user_data['nama']}** ({user_role.upper()})")
    st.sidebar.markdown("---")
    
    if user_role == "admin":
        menu = st.sidebar.selectbox("Menu Admin", ["Dashboard Utama & Scanner", "Profil Pengguna"])
    else:
        menu = st.sidebar.selectbox("Menu Mahasiswa", ["Profil", "Daftar Kendaraan", "Lihat Data Kendaraan"])
        
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout / Keluar", use_container_width=True):
        log_activity(user_id, "logout")
        st.session_state.user = None
        st.session_state.page = "login"
        st.rerun()

    # =========================================================================
    # TAMPILAN 1: DASHBOARD UTAMA ADMIN + KAMERA SCANNER + MONITOR GATE
    # =========================================================================
    if user_role == "admin" and menu == "Dashboard Utama & Scanner":
        st.header("📋 Dashboard Utama Petugas")
        
        # --- LOGIKA TIMER HITUNG MUNDUR (DARI KODE PERTAMA) ---
        time_elapsed = datetime.now() - st.session_state.monitor_display_time
        if st.session_state.monitor_type != 'default' and time_elapsed.total_seconds() >= 5:
            # Kembalikan monitor ke tampilan stanby setelah 5 detik
            st.session_state.monitor_html = "<div style='background-color: #f1f3f5; color: #495057; padding: 20px; border-radius: 5px; text-align: center; height: 50vh; display: flex; flex-direction: column; justify-content: center;'><h1 style='font-size: 50px;'>🅿️ MONITOR GATE READY</h1><p style='font-size: 20px;'>Silakan lakukan scan QR Code pada kamera di bawah.</p></div>"
            st.session_state.monitor_type = 'default'
            st.rerun()

        # Tampilkan Kotak Monitor Elektronik atas Gerbang
        st.markdown(st.session_state.monitor_html, unsafe_allow_html=True)
        
        # Jika status monitor sedang memproses teks sambutan, jalankan simulasi hitung mundur
        if st.session_state.monitor_type != 'default' and time_elapsed.total_seconds() < 5:
            time_left = 5 - int(time_elapsed.total_seconds())
            st.caption(f"⏳ Layar monitor kembali normal dalam {time_left} detik...")
            time.sleep(1)
            st.rerun()
            
        st.markdown("---")
        
        # --- FITUR SCANNER / KAMERA INPUT ---
        st.subheader("📸 Kamera Scanner Masuk / Keluar")
        scan_input = st.text_input("Simulasi Scan QR Code (Ketik/Gunakan Scanner Barcode di sini):", key="scanner_field").strip()
        
        if st.button("Proses Scan QR", type="primary", use_container_width=True) and scan_input:
            if db:
                try:
                    # Pecah data QR (Format pendaftaran: nama-nim-plat)
                    qr_parts = scan_input.split('-')
                    if len(qr_parts) >= 3:
                        target_plat = qr_parts[2]
                    else:
                        target_plat = scan_input # jika yang di-scan langsung plat nomornya
                    
                    # Cari kendaraan berdasarkan plat nomor di Firebase
                    v_query = list(db.collection("vehicles").where("plat", "==", target_plat).limit(1).get())
                    
                    if v_query:
                        doc = v_query[0]
                        v_data = doc.to_dict()
                        current_status = v_data.get("status", "OUT")
                        driver_name = v_data.get("nama", "Pengguna")
                        
                        now_time = datetime.now()
                        
                        if current_status == "OUT" or current_status == "pending":
                            # Aksi: MASUK KAMPUS
                            db.collection("vehicles").document(doc.id).update({
                                "status": "IN",
                                "time_in": now_time,
                                "time_out": None,
                                "duration": ""
                            })
                            log_activity(v_data.get("user_id"), f"Masuk Parkir ({target_plat})")
                            
                            # Update visual monitor ke LAYAR HIJAU (Selamat Datang)
                            st.session_state.monitor_html = f"<div style='background-color: #d4edda; color: #155724; padding: 40px; border-radius: 10px; text-align: center; min-height: 40vh; display: flex; flex-direction: column; justify-content: center;'><h1 style='font-size: 60px;'>✅ SELAMAT DATANG!</h1><p style='font-size: 35px; font-weight: bold;'>{driver_name}</p><p style='font-size: 25px;'>Plat Nomor: {target_plat} | Akses Diberikan</p></div>"
                            st.session_state.monitor_type = 'IN'
                            st.session_state.monitor_display_time = datetime.now()
                            st.rerun()
                            
                        else:
                            # Aksi: KELUAR KAMPUS
                            time_in = v_data.get("time_in")
                            duration_str = "Tidak Terdeteksi"
                            if time_in:
                                # Jika objek time_in dari Firebase berupa timestamp, ubah ke python datetime
                                if hasattr(time_in, 'timestamp'):
                                    time_in = datetime.fromtimestamp(time_in.timestamp())
                                duration = now_time - time_in
                                duration_str = str(duration).split('.')[0]
                                
                            db.collection("vehicles").document(doc.id).update({
                                "status": "OUT",
                                "time_out": now_time,
                                "duration": duration_str
                            })
                            log_activity(v_data.get("user_id"), f"Keluar Parkir ({target_plat})")
                            
                            # Update visual monitor ke LAYAR KUNING (Selamat Jalan)
                            st.session_state.monitor_html = f"<div style='background-color: #fff3cd; color: #856404; padding: 40px; border-radius: 10px; text-align: center; min-height: 40vh; display: flex; flex-direction: column; justify-content: center;'><h1 style='font-size: 60px;'>🚪 SAMPAI JUMPA LAGI</h1><p style='font-size: 35px; font-weight: bold;'>{driver_name}</p><p style='font-size: 25px;'>Durasi Parkir: {duration_str}</p></div>"
                            st.session_state.monitor_type = 'OUT'
                            st.session_state.monitor_display_time = datetime.now()
                            st.rerun()
                    else:
                        # Layar Merah jika tidak terdaftar
                        st.session_state.monitor_html = "<div style='background-color: #f8d7da; color: #721c24; padding: 40px; border-radius: 10px; text-align: center; min-height: 40vh; display: flex; flex-direction: column; justify-content: center;'><h1 style='font-size: 60px;'>❌ ERROR SECURE!</h1><p style='font-size: 30px; font-weight: bold;'>QR CODE / PLAT TIDAK TERDAFTAR</p></div>"
                        st.session_state.monitor_type = 'ERROR'
                        st.session_state.monitor_display_time = datetime.now()
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Gagal memproses pemicu scanner database: {e}")
            else:
                st.error("Koneksi Firebase Database terputus.")

        # --- TABEL MONITOR DATA REAL-TIME ---
        st.markdown("---")
        st.subheader("📊 Tabel Status Kendaraan Real-Time")
        if db:
            try:
                vehicles_ref = db.collection("vehicles").stream()
                vehicles_list = []
                for v in vehicles_ref:
                    v_data = v.to_dict()
                    
                    # Formatting tanggal dari Firebase agar rapi di tabel Pandas
                    t_in = v_data.get("time_in")
                    t_out = v_data.get("time_out")
                    t_in_str = t_in.strftime("%d-%m-%Y %H:%M:%S") if hasattr(t_in, 'strftime') else "-"
                    t_out_str = t_out.strftime("%d-%m-%Y %H:%M:%S") if hasattr(t_out, 'strftime') else "-"
                    
                    vehicles_list.append({
                        "Nama Pemilik": v_data.get("nama", "-"),
                        "NIM": v_data.get("nim", "-"),
                        "Plat Nomor": v_data.get("plat", "-"),
                        "Jenis": v_data.get("jenis", "-"),
                        "Status": "📍 DI DALAM" if v_data.get("status") == "IN" else "🚗 LUAR KAMPUS",
                        "Waktu Masuk": t_in_str,
                        "Waktu Keluar": t_out_str,
                        "Durasi Terakhir": v_data.get("duration", "-")
                    })
                
                if vehicles_list:
                    st.dataframe(pd.DataFrame(vehicles_list), use_container_width=True)
                else:
                    st.info("Belum ada data kendaraan terdaftar di Firebase Cloud.")
            except Exception as e:
                st.error(f"Gagal memuat log tabel utama: {e}")

    # =========================================================================
    # HALAMAN LAIN (PROFIL, DAFTAR KENDARAAN, LIHAT DATA)
    # =========================================================================
    elif menu == "Profil" or menu == "Profil Pengguna":
        st.header("Profil Pengguna")
        st.write(f"Nama: {user_data['nama']}")
        st.write(f"NIM/NIP: {user_data['nim']}")
        st.write(f"Email: {user_data['email']}")
        
        st.subheader("Log Aktivitas Akun")
        logs = get_user_logs(user_id)
        if logs:
            processed_logs = []
            for l in logs:
                try:
                    ts_obj = l.get('timestamp')
                    ts_str = ts_obj.strftime("%d-%m-%Y %H:%M:%S") if ts_obj else "Waktu Tidak Tersedia"
                except:
                    ts_str = "Error Konversi"
                processed_logs.append({"Aktivitas": l.get('action', 'N/A').capitalize(), "Waktu Log": ts_str})
            st.dataframe(pd.DataFrame(processed_logs), use_container_width=True, hide_index=True)
        else:
            st.info("Belum ada riwayat log aktivitas.")

    elif menu == "Daftar Kendaraan":
        st.header("Form Pendaftaran Kendaraan Baru")
        nama_k = st.text_input("Nama Lengkap", value=user_data['nama'], disabled=True)
        nim_k = st.text_input("NIM", value=user_data['nim'], disabled=True)
        plat = st.text_input("Masukkan Plat Nomor Kendaraan (Contoh: B1234XYZ)").upper().strip()
        jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
        foto = st.file_uploader("Upload Foto Fisik Kendaraan", type=["jpg","jpeg","png"])

        if st.button("Daftar & Terbitkan Akses QR", type="primary"):
            if plat and foto:
                import tempfile
                tmp_dir = tempfile.gettempdir()
                
                # Simpan berkas gambar sementara
                tmp_foto_path = os.path.join(tmp_dir, f"{plat}_foto.png")
                with open(tmp_foto_path, "wb") as f:
                    f.write(foto.getbuffer())
                
                # Mengunggah data ke Storage Firebase Cloud
                st.info("Sedang mendaftarkan berkas ke cloud...")
                foto_url = upload_to_storage(tmp_foto_path, f"foto/{plat}.png")

                # Membangun QR Code Otomatis
                qr_data = f"{user_data['nama']}-{user_data['nim']}-{plat}"
                qr_filename = os.path.join(tmp_dir, f"qr_{plat}.png")
                img = qrcode.make(qr_data)
                img.save(qr_filename)
                qr_url = upload_to_storage(qr_filename, f"qr/{plat}.png")

                if foto_url and qr_url:
                    save_data_firestore(user_id, user_data['nama'], user_data['nim'], plat, jenis, foto_url, qr_url)
                    st.success(f"✅ Registrasi sukses! Plat {plat} siap digunakan.")
                    st.image(qr_filename, caption="Gunakan QR Code ini untuk scan di gerbang.")
                else:
                    st.error("Gagal melakukan upload berkas.")
                    
                if os.path.exists(tmp_foto_path): os.remove(tmp_foto_path)
                if os.path.exists(qr_filename): os.remove(qr_filename)
            else:
                st.error("Mohon isi nomor plat kendaraan dan lampirkan foto fisik.")

    elif menu == "Lihat Data Kendaraan":
        st.header("Kartu Identitas Parkir Saya")
        data = get_user_vehicles(user_id)
        if data:
            for d in data:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"🏷️ Plat: {d['plat']}")
                    st.write(f"Jenis: {d['jenis']}")
                    st.write(f"Status Saat Ini: {d.get('status', 'OUT')}")
                    st.image(d["qr_url"], caption="QR Code Scan Akses", width=200)
                with col2:
                    st.image(d["foto_url"], caption="Foto Fisik Kendaraan", width=250)
                st.markdown("---")
        else:
            st.info("Anda belum mendaftarkan kendaraan apa pun.")

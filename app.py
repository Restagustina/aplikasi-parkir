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
try:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            # Pastikan ID Proyek Anda benar
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
    # Digunakan untuk hashing password user dan admin
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

# --- FUNGSI QR CODE OTOMATIS ---
def generate_and_store_qr(user_id, identifier_data, user_role, user_nim):
    """
    Membuat QR Code dengan data User ID, mengupload ke Storage,
    dan menyimpan URL-nya di dokumen pengguna.
    """
    if not bucket or not db:
        st.error("Koneksi Firebase gagal, QR Code tidak dapat dibuat.")
        return None
        
    # 1. Tentukan Data QR
    # Data QR adalah format: ROLE:UID (contoh: MHS:abcdef123)
    qr_data = f"{user_role.upper()}:{user_id}" 
    filename = f"qr_user_{user_nim}.png"
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
            
            # 5. Update session state
            st.session_state.user['qr_identitas_url'] = qr_url
            
            # 6. PENTING: Memicu rerun agar QR Code langsung ditampilkan
            st.toast("ID Digital (QR Code) berhasil dibuat!", icon="✅")
            st.rerun()
            return qr_url
        else:
            return None
    except Exception as e:
        st.error(f"Gagal memproses QR Code: {e}")
        return None
    finally:
        if os.path.exists(qr_path):
            os.remove(qr_path)

# --- FUNGSI GET LOGS ---
def get_user_logs(user_id):
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

def get_all_vehicles():
    """Mengambil semua data kendaraan (digunakan oleh Admin)."""
    if db:
        vehicles_ref = db.collection("vehicles").stream()
        return [veh.to_dict() for veh in vehicles_ref]
    return []

# --- FUNGSI FIREBASE LAIN ---

def register_user(nama, nim, email, password, role):
    """Mendaftarkan pengguna baru ke Firestore dengan peran."""
    if db:
        # Cek duplikasi email
        users_ref = list(db.collection("users").where("email", "==", email).limit(1).get())
        if users_ref:
            return None

        hashed_password = hash_password(password)
        doc_ref = db.collection("users").add({
            "nama": nama,
            "nim": nim, # Gunakan NIM/NIP sebagai identifier utama
            "email": email,
            "password_hash": hashed_password,
            "role": role, # Peran (mahasiswa, dosen, staff, tamu)
            "created_at": firestore.SERVER_TIMESTAMP,
            "qr_identitas_url": "" # Field untuk QR otomatis
        })
        # Ambil data yang baru dibuat untuk dikembalikan
        new_user_doc = db.collection("users").document(doc_ref[1].id).get().to_dict()
        return {"uid": doc_ref[1].id, **new_user_doc}
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
            # Error 404 muncul di sini
            st.error(f"Gagal upload ke Storage: {e}")
            return None
    return None

def save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url, role):
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
            "role": role,
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
st.set_page_config(page_title="Digital ID Parkir Fasilkom", page_icon="🅿️", layout="wide")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login_selector" # Halaman awal: Pemilih Role
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "admin_login_open" not in st.session_state:
    st.session_state.admin_login_open = False


# --- FUNGSI & PANGGILAN BACKGROUND IMAGE ---
# ... (Fungsi set_background dan get_base64)
def get_base64(bin_file):
    if not os.path.exists(bin_file):
        # Handle the case where the image file is not found
        # (Menggunakan salah satu gambar yang diupload sebagai pengganti jika ada)
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

# PANGGIL FUNGSI LATAR BELAKANG
set_background('BG FASILKOM.jpg')


# ---------------- CUSTOM CSS UNTUK ADMIN LOGIN (BUTTON KUNCI) ----------------
st.markdown("""
<style>
/* CSS untuk menempatkan tombol kunci di pojok kiri atas (halaman login) */
.admin-key-button {
    position: fixed;
    top: 15px;
    left: 15px;
    z-index: 1000;
}
.admin-key-button button {
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 5px;
    padding: 10px;
    color: white;
    cursor: pointer;
    backdrop-filter: blur(5px);
    transition: background 0.3s;
}
.admin-key-button button:hover {
    background: rgba(255, 255, 255, 0.4);
}
</style>
""", unsafe_allow_html=True)

# ---------------- FUNGSI HALAMAN ----------------

def show_admin_login():
    """Menampilkan modal login admin jika admin_login_open True."""
    
    # Tombol Kunci di pojok kiri atas
    st.markdown(
        f"""
        <div class="admin-key-button">
            <button onclick="window.parent.document.querySelector('[data-testid=\"stFullScreenFrame\"] > div > div > div:nth-child(2) > div').style.display = 'none';">
                🔑 Admin Login
            </button>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.admin_login_open and not st.session_state.admin_logged_in:
        
        # Modal/Pop-up untuk Login Admin
        with st.form("admin_login_form", clear_on_submit=False):
            st.markdown("### 🔒 Akses Admin")
            admin_user = st.text_input("Username", key="admin_user_input")
            admin_pass = st.text_input("Password", type="password", key="admin_pass_input")
            
            submitted = st.form_submit_button("Masuk sebagai Admin")
            
            if submitted:
                if admin_user == st.secrets["admin_user"]["username"] and \
                   hash_password(admin_pass) == st.secrets["admin_user"]["password_hash"]:
                    
                    st.session_state.admin_logged_in = True
                    st.session_state.user = {"uid": "ADMIN_ID", "nama": "Admin", "role": "admin"} # Role admin
                    st.session_state.page = "app"
                    st.session_state.admin_login_open = False
                    log_activity("ADMIN_ID", "login admin")
                    st.rerun()
                else:
                    st.error("Username atau Password Admin salah!")

        if st.button("Tutup", key="close_admin_login"):
            st.session_state.admin_login_open = False
            st.rerun()


# --- STARTING PAGE: ROLE SELECTOR ---
if st.session_state.page == "login_selector":
    
    # Tampilkan Tombol Admin Login di pojok kiri
    # Toggle state admin_login_open
    if st.button("🔑 Admin Login", key="toggle_admin_login_button"):
        st.session_state.admin_login_open = not st.session_state.admin_login_open
        st.rerun()
        
    if st.session_state.admin_login_open:
        # Tampilkan Form Login Admin di Pop-up
        st.subheader("🔒 Login Admin")
        with st.form("admin_login_form_2", clear_on_submit=False):
            admin_user = st.text_input("Username", key="admin_user_input_2")
            admin_pass = st.text_input("Password", type="password", key="admin_pass_input_2")
            submitted = st.form_submit_button("Masuk sebagai Admin")
            
            if submitted:
                if admin_user == st.secrets["admin_user"]["username"] and \
                   hash_password(admin_pass) == st.secrets["admin_user"]["password_hash"]:
                    
                    st.session_state.admin_logged_in = True
                    st.session_state.user = {"uid": "ADMIN_ID", "nama": "Admin", "role": "admin"} 
                    st.session_state.page = "app"
                    st.session_state.admin_login_open = False
                    log_activity("ADMIN_ID", "login admin")
                    st.rerun()
                else:
                    st.error("Username atau Password Admin salah!")
        
        if st.button("Tutup Form Admin", key="close_admin_login_2"):
            st.session_state.admin_login_open = False
            st.rerun()
        
        st.markdown("---") # Garis pemisah antara form admin dan selector user
        
    st.markdown("### Masuk Sebagai:")
    
    col1, col2, col3, col4 = st.columns(4)
    
    roles = ["Mahasiswa", "Dosen", "Staff", "Tamu"]
    
    for i, role in enumerate(roles):
        with [col1, col2, col3, col4][i]:
            if st.button(role, key=f"select_role_{role}", use_container_width=True):
                st.session_state.selected_role = role
                st.session_state.page = "login"
                st.rerun()


# ---------------- USER LOGIN PAGE ----------------
elif st.session_state.page == "login" and st.session_state.user is None:
    st.markdown(f"### 🔑 Login {st.session_state.selected_role}") 

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        submitted = st.form_submit_button(f"Masuk sebagai {st.session_state.selected_role}")

        if submitted:
            if db:
                users = db.collection("users").where("email", "==", email).where("role", "==", st.session_state.selected_role.lower()).stream()
                user_found = False
                for u in users:
                    u_data = u.to_dict()
                    if u_data.get("password_hash") == hash_password(password):
                        st.session_state.user = {"uid": u.id, **u_data}
                        log_activity(u.id, "login")
                        st.success(f"Selamat datang, {u_data.get('nama')}!")
                        user_found = True
                        st.session_state.page = "app"
                        st.rerun() 
                        break
                if not user_found:
                    st.error(f"Akun tidak ditemukan atau peran tidak sesuai ({st.session_state.selected_role})!")
            else:
                st.error("Koneksi ke database gagal.")

    if st.button("Daftar Akun Baru", key="goto_register"):
        st.session_state.page = "register"
        st.rerun() 
    
    if st.button("Kembali ke Pilihan Peran", key="back_to_selector"):
        st.session_state.page = "login_selector"
        st.rerun()

# ---------------- REGISTER PAGE ----------------
elif st.session_state.page == "register" and st.session_state.user is None:
    role_options = ["Mahasiswa", "Dosen", "Staff", "Tamu"]
    st.subheader("📝 Form Registrasi User Baru")
    
    # Input Peran Saat Registrasi
    reg_role = st.selectbox("Daftar sebagai:", role_options, key="reg_role_select")

    reg_nama = st.text_input("Nama Lengkap", key="reg_nama")
    reg_nim_label = "NIM/NIP/ID Lain" if reg_role != "Mahasiswa" else "NIM"
    reg_nim = st.text_input(reg_nim_label, key="reg_nim")
    reg_email = st.text_input("Email", key="reg_email")
    reg_password = st.text_input("Password", type="password", key="reg_password")
    reg_password2 = st.text_input("Konfirmasi Password", type="password", key="reg_password2")

    if st.button("Daftar Sekarang", key="btn_register"):
        if reg_password != reg_password2:
            st.error("Password dan konfirmasi tidak sama!")
        elif reg_nama and reg_nim and reg_email and reg_password:
            # Panggil fungsi register
            new_user_data = register_user(reg_nama, reg_nim, reg_email, reg_password, reg_role.lower()) 
            
            if new_user_data:
                # Login otomatis setelah daftar
                st.session_state.user = new_user_data
                st.session_state.page = "app"
                st.success("Akun berhasil dibuat! Anda otomatis masuk.")
                st.rerun() 
            else:
                st.error("Email sudah terdaftar!")
        else:
            st.error("Lengkapi semua data!")

    if st.button("Kembali ke Login", key="back_login"):
        st.session_state.page = "login_selector"
        st.rerun() 

# ---------------- APP UTAMA (USER & ADMIN) ----------------
elif st.session_state.user and st.session_state.page == "app":
    
    user_id = st.session_state.user['uid']
    user_role = st.session_state.user['role']
    
    # ------------------ LOGIKA GENERATE QR OTOMATIS (USER SAJA) ------------------
    # Cek hanya jika bukan Admin dan QR belum ada
    if user_role != "admin" and ('qr_identitas_url' not in st.session_state.user or st.session_state.user.get('qr_identitas_url') == ""):
        with st.spinner(f'Sistem sedang membuat ID Digital ({user_role.capitalize()}) Anda secara otomatis...'):
             generate_and_store_qr(
                user_id=user_id,
                identifier_data=st.session_state.user['email'],
                user_role=user_role,
                user_nim=st.session_state.user['nim']
             )
        # Jika berhasil, st.rerun() sudah dipanggil di dalam fungsi.
    # -----------------------------------------------------------------------------

    st.sidebar.title("Menu")
    
    if user_role == "admin":
        st.success(f"Selamat datang, {st.session_state.user['nama']} (Administrator)!")
        menu_options = ["Dashboard Admin", "Data Kendaraan Terdaftar", "Log Aktivitas Global"]
    else:
        st.success(f"Selamat datang, {st.session_state.user['nama']} ({user_role.capitalize()})!")
        menu_options = ["ID Digital (QR Code)", "Daftar Kendaraan", "Lihat Data Kendaraan", "Profil & Log"]
        
    menu = st.sidebar.selectbox("", menu_options)
    
    if st.sidebar.button("Logout"):
        log_activity(user_id, "logout")
        st.session_state.user = None
        st.session_state.admin_logged_in = False
        st.session_state.page = "login_selector"
        st.rerun() 

    # =========================================================================
    # --- ADMIN PAGES ---
    # =========================================================================
    if user_role == "admin":
        
        if menu == "Dashboard Admin":
            st.header("Dashboard Administrator")
            st.info("Di sini Admin dapat melihat ringkasan aktivitas dan status pendaftaran.")
            # Anda bisa menambahkan statistik: jumlah user, jumlah kendaraan pending, dll.

        elif menu == "Data Kendaraan Terdaftar":
            st.header("Manajemen Kendaraan")
            all_vehicles = get_all_vehicles()
            
            if all_vehicles:
                # Konversi ke DataFrame untuk tampilan yang rapi
                df_vehicles = pd.DataFrame(all_vehicles)
                
                # Saring kolom yang relevan untuk Admin
                display_cols = ['nama', 'nim', 'role', 'plat', 'jenis', 'status', 'created_at']
                df_display = df_vehicles[display_cols].rename(columns={'nim': 'NIM/ID', 'plat': 'Plat Nomor', 'role': 'Peran', 'created_at': 'Tanggal Daftar'})
                
                st.dataframe(df_display, use_container_width=True)
                
                # Implementasi tombol aksi (contoh: Approve)
                st.subheader("Aksi Kendaraan (Contoh)")
                # (Di sini Anda perlu menambahkan logika untuk update status di Firestore)
                # Contoh: plat_to_approve = st.selectbox("Pilih Plat untuk Approve", df_vehicles['plat'].tolist())
                # if st.button("Approve Kendaraan"):
                #    # Logika update db.collection("vehicles")...
                #    st.success(f"Plat {plat_to_approve} disetujui.")
                
                st.markdown("---")
                
                # Tampilkan detail foto/QR jika dipilih
                # (Anda bisa menambahkan logika filter/pencarian di sini)
                
            else:
                st.info("Belum ada data kendaraan yang didaftarkan.")
                
        elif menu == "Log Aktivitas Global":
            st.header("Log Aktivitas Global")
            # Logika untuk mengambil SEMUA log
            st.warning("Fitur ini membutuhkan Query Indexing yang kompleks atau harus diimplementasikan dengan Batasan waktu/jumlah.")
            
            # Untuk demo, kita bisa tampilkan log Admin sendiri
            logs = get_user_logs(user_id) 
            st.subheader("Log Aktivitas Admin")
            if logs:
                 # Logic to process and display logs remains the same as in User Profil
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
            else:
                st.info("Belum ada aktivitas admin.")


    # =========================================================================
    # --- USER PAGES ---
    # =========================================================================
    else: # Role selain admin (Mahasiswa, Dosen, Staff, Tamu)

        # ---------- ID DIGITAL (QR CODE) ----------
        if menu == "ID Digital (QR Code)":
            st.header(f"ID Digital ({user_role.capitalize()})")
            qr_url = st.session_state.user.get('qr_identitas_url')

            if qr_url and qr_url != "":
                st.success("QR Code ID Digital Anda siap digunakan.")
                st.image(qr_url, caption=f"ID Digital: {user_role.capitalize()}", width=300)
                
                # Tombol download
                st.markdown(f'<a href="{qr_url}" download="qr_identitas_{st.session_state.user["nim"]}.png" target="_blank"><button style="background-color: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Download QR Code</button></a>', unsafe_allow_html=True)
                
            else:
                st.warning("QR Code Anda sedang dalam proses pembuatan. Mohon tunggu sejenak atau refresh halaman.")

        # ---------- DAFTAR KENDARAAN ----------
        elif menu == "Daftar Kendaraan":
            st.header("Form Pendaftaran Kendaraan")
            st.info(f"Anda mendaftar sebagai **{user_role.capitalize()}**.")
            
            nama = st.text_input("Nama Lengkap", value=st.session_state.user['nama'], disabled=True)
            nim = st.text_input("NIM/ID", value=st.session_state.user['nim'], disabled=True)
            
            plat = st.text_input("Plat Nomor")
            jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
            foto = st.file_uploader("Upload Foto Kendaraan", type=["jpg","jpeg","png"])

            if st.button("Daftar Kendaraan"):
                if plat and jenis and foto:
                    tmp_dir = tempfile.gettempdir()
                    # Simpan foto ke temp file
                    tmp_foto_path = os.path.join(tmp_dir, f"{plat}_foto.png")
                    with open(tmp_foto_path, "wb") as f:
                        f.write(foto.getbuffer())
                    
                    foto_url = upload_to_storage(tmp_foto_path, f"foto/{plat}.png")

                    # QR Kendaraan (Untuk membedakan QR ID Digital dan QR Kendaraan)
                    qr_data = f"VEHICLE:{plat}"
                    qr_filename = os.path.join(tmp_dir, f"qr_kendaraan_{plat}.png")
                    img = qrcode.make(qr_data)
                    img.save(qr_filename)
                    qr_url = upload_to_storage(qr_filename, f"qr_kendaraan/{qr_filename}")

                    if foto_url and qr_url:
                        # Simpan data ke Firestore (termasuk role)
                        save_data_firestore(user_id, nama, nim, plat, jenis, foto_url, qr_url, user_role)

                        st.success("✅ Data kendaraan berhasil disimpan! Menunggu persetujuan Admin.")
                        st.image(qr_filename, caption="QR Code Kendaraan (Sementara)", width=150)
                    else:
                        st.error("Gagal mengupload file ke Storage! Periksa koneksi Firebase Anda.")

                    if os.path.exists(tmp_foto_path):
                        os.remove(tmp_foto_path)
                    if os.path.exists(qr_filename):
                        os.remove(qr_filename)
                else:
                    st.error("⚠️ Lengkapi semua data dan upload foto kendaraan.")

        # ---------- LIHAT DATA KENDARAAN ----------
        elif menu == "Lihat Data Kendaraan":
            st.header("Data Kendaraan Saya")
            data = get_user_vehicles(user_id) 
            if data:
                for d in data:
                    st.subheader(f"{d['plat']} ({d['jenis']})")
                    st.write(f"Status Pendaftaran: **{d['status'].capitalize()}**")
                    st.write(f"Pemilik: {d['nama']} ({d['nim']})")
                    st.image(d["foto_url"], caption="Foto Kendaraan", width=200)
                    st.image(d["qr_url"], caption="QR Code Kendaraan", width=150)
                    st.markdown("---")
            else:
                st.info("Belum ada data kendaraan yang terdaftar.")
                
        # ---------- PROFIL & LOG ----------
        elif menu == "Profil & Log":
            st.header(f"Profil Pengguna ({user_role.capitalize()})")
            st.write(f"Nama: {st.session_state.user['nama']}")
            st.write(f"ID Utama: {st.session_state.user['nim']}")
            st.write(f"Email: {st.session_state.user['email']}")

            st.subheader("Log Aktivitas Saya (100 Terbaru)")
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

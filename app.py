import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import qrcode
import tempfile
import os

# ---------------- FIREBASE SETUP ----------------
# File JSON dari Firebase (service account)
cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "storageBucket": "parkir-mahasiswa.appspot.com"  # ganti dengan bucket Storage kamu
    })

db = firestore.client()
bucket = storage.bucket()

# ---------------- HELPER FUNCTIONS ----------------
def save_data_firestore(nama, nim, plat, jenis, foto_url, qr_url):
    """Simpan data kendaraan ke Firestore"""
    data = {
        "nama": nama,
        "nim": nim,
        "plat": plat,
        "jenis": jenis,
        "foto_url": foto_url,
        "qr_url": qr_url
    }
    db.collection("kendaraan").add(data)

def upload_to_storage(file_path, filename):
    """Upload file ke Firebase Storage dan return URL publik"""
    blob = bucket.blob(filename)
    blob.upload_from_filename(file_path)
    blob.make_public()
    return blob.public_url

def get_all_data():
    """Ambil semua data kendaraan dari Firestore"""
    docs = db.collection("kendaraan").stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        data.append(d)
    return data

# ---------------- STREAMLIT APP ----------------
st.title("Digital ID Parkir Mahasiswa (Firebase)")

menu = st.sidebar.selectbox("Menu", ["Daftar Kendaraan", "Lihat Data Kendaraan"])

if menu == "Daftar Kendaraan":
    st.header("Form Pendaftaran Kendaraan")

    nama = st.text_input("Nama Lengkap")
    nim = st.text_input("NIM")
    plat = st.text_input("Plat Nomor")
    jenis = st.selectbox("Jenis Kendaraan", ["Motor", "Mobil", "Lainnya"])
    foto = st.file_uploader("Upload Foto Kendaraan", type=["jpg", "jpeg", "png"])

    if st.button("Daftar"):
        if nama and nim and plat and jenis and foto:
            # Simpan foto sementara
            tmp_foto = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_foto.write(foto.getbuffer())
            tmp_foto.close()

            # Upload foto ke Firebase Storage
            foto_url = upload_to_storage(tmp_foto.name, f"foto/{plat}.png")

            # Generate QR Code
            qr_data = f"{nama}-{nim}-{plat}"
            qr_filename = f"qr_{plat}.png"
            img = qrcode.make(qr_data)
            img.save(qr_filename)

            # Upload QR ke Firebase Storage
            qr_url = upload_to_storage(qr_filename, f"qr/{qr_filename}")

            # Simpan data ke Firestore
            save_data_firestore(nama, nim, plat, jenis, foto_url, qr_url)

            st.success("✅ Data kendaraan berhasil disimpan!")
            st.image(qr_filename, caption="QR Code Parkir Anda")

            # Bersihkan file sementara
            os.remove(tmp_foto.name)
            os.remove(qr_filename)
        else:
            st.error("⚠️ Lengkapi semua data dan upload foto kendaraan.")

elif menu == "Lihat Data Kendaraan":
    st.header("Data Kendaraan Terdaftar")

    data = get_all_data()
    if data:
        for d in data:
            st.subheader(f"{d['nama']} ({d['nim']})")
            st.write(f"Plat: {d['plat']} | Jenis: {d['jenis']}")
            st.image(d["foto_url"], caption="Foto Kendaraan", width=200)
            st.image(d["qr_url"], caption="QR Code", width=150)
            st.markdown("---")
    else:
        st.info("Belum ada data kendaraan yang terdaftar.")
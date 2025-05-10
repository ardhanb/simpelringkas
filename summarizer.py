import httpx
import time
from collections import deque

API_KEY = "Bearer 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"  # Ganti dengan API asli kamu
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

def generate_prompt(text, language="id", summary_type="narrative", tone="simple"):
    if language == "id":
        return f"""
Kamu adalah asisten akademik yang terlatih dalam merangkum isi utama dari jurnal ilmiah dan artikel penelitian. Berikut adalah isi dokumen akademik.

Tolong buatkan ringkasan naratif yang menyeluruh dan profesional dalam Bahasa Indonesia.
Ringkasan harus mencakup:
- Topik utama
- Tujuan penulisan
- Argumen atau temuan penting
- Kesimpulan atau implikasi

Gunakan bahasa akademik yang padat namun tetap jelas.

{text}

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
- Final conclusion or implication

Use academic tone and professional language.


{text}
"""

def summarize_page(text, language="id", mode="page"):
    prompt = generate_prompt(text, language, mode)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional summarization assistant, who knows all different themes very well."},
            {"role": "user", "content": prompt.strip()}
        ]
    }
    headers = {
        "Authorization": API_KEY,
        "Content-Type": "application/json"
    }
    try:
        timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=5.0)
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout
        )
        if response.status_code != 200:
            return f"[Gagal ringkas] Status: {response.status_code}\nDetail: {response.text}"
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Groq Error]: {str(e)}"

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

    combined_summary = "\n\n".join(intermediate_summaries)
    final_prompt = f"""
Berikut adalah ringkasan per bagian dari dokumen:

{combined_summary}

Gabungkan semua ringkasan ini menjadi satu ringkasan akhir yang menyeluruh, rapi, dan terstruktur.
"""
    wait_for_token_availability(estimate_tokens(final_prompt) + 1000)
    return summarize_page(final_prompt, language, "full")

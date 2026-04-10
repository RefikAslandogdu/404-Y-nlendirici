from flask import Flask, render_template, request, jsonify, send_file
from urllib.parse import urlparse, unquote
from rapidfuzz import fuzz
import openpyxl
import tempfile
import os
import re

app = Flask(__name__)


def clean_path(url):
    """URL'den temiz path çıkar."""
    parsed = urlparse(unquote(url))
    path = parsed.path.strip("/").lower()
    path = re.sub(r"\.(html?|php|aspx?|jsp)$", "", path, flags=re.IGNORECASE)
    return path


def extract_keywords(url):
    """URL'den anlamlı anahtar kelimeleri çıkar."""
    path = clean_path(url)
    tokens = re.split(r"[-_/+.,]", path)
    keywords = [t.lower() for t in tokens if len(t) > 1]
    return keywords


def find_homepage(active_urls):
    """Aktif URL'ler arasından anasayfayı bul."""
    for url in active_urls:
        path = urlparse(url).path.strip("/")
        if not path or path in ("index", "index.html", "anasayfa", "home"):
            return url
    return min(active_urls, key=lambda u: len(urlparse(u).path.strip("/")))


def build_patterns(active_urls):
    """Aktif URL'lerden regex pattern'ları oluştur.
    Her aktif URL'nin slug parçalarından pattern üretilir."""
    patterns = []
    for url in active_urls:
        path = clean_path(url)
        if not path:
            continue
        # URL'nin segmentlerini al
        segments = [s for s in path.split("/") if s]
        # Her segmentteki kelimeleri çıkar
        all_words = []
        for seg in segments:
            words = [w for w in re.split(r"[-_+.,]", seg) if len(w) > 2]
            all_words.extend(words)

        if not all_words:
            continue

        # Bu URL için regex: slug içinde bu kelimelerden en az biri geçmeli
        word_pattern = "|".join(re.escape(w) for w in all_words)
        patterns.append({
            "url": url,
            "regex": re.compile(word_pattern, re.IGNORECASE),
            "words": set(all_words),
            "segments": segments,
        })
    return patterns


def score_match(redirect_url, active_pattern):
    """404 URL ile bir aktif URL pattern'ı arasındaki skoru hesapla."""
    redirect_path = clean_path(redirect_url)
    redirect_words = set(re.split(r"[-_/+.,]", redirect_path))
    redirect_words = {w.lower() for w in redirect_words if len(w) > 2}
    redirect_segments = [s for s in redirect_path.split("/") if s]

    active_words = active_pattern["words"]
    active_segments = active_pattern["segments"]

    # 1) Tam yol eşleşmesi
    active_path = clean_path(active_pattern["url"])
    if redirect_path == active_path:
        return 100.0

    # 2) Regex eşleşmesi — pattern redirect URL'de geçiyor mu?
    regex_matches = active_pattern["regex"].findall(redirect_path)
    unique_matches = set(m.lower() for m in regex_matches)
    if not unique_matches:
        return 0.0  # Hiç regex eşleşmesi yoksa skor 0

    # 3) Eşleşen kelime oranı
    match_ratio = len(unique_matches) / max(len(active_words), 1)
    word_score = match_ratio * 60

    # 4) Segment (kategori) eşleşmesi
    common_segments = sum(1 for s in redirect_segments if s in active_segments)
    segment_score = (common_segments / max(len(active_segments), len(redirect_segments), 1)) * 25

    # 5) Fuzzy bonus (sadece regex eşleşenler için)
    fuzzy_score = fuzz.token_sort_ratio(redirect_path, active_path) * 0.15

    final_score = word_score + segment_score + fuzzy_score
    return round(min(final_score, 100.0), 1)


def find_best_match(redirect_url, active_urls, patterns):
    """404 URL için en iyi eşleşen aktif URL'yi bul.
    Hiçbir pattern eşleşmezse anasayfaya yönlendir."""
    best_url = None
    best_score = 0

    for pattern in patterns:
        score = score_match(redirect_url, pattern)
        if score > best_score:
            best_score = score
            best_url = pattern["url"]

    # Hiçbir regex eşleşmesi yoksa (skor 0) → anasayfa
    if best_score == 0:
        homepage = find_homepage(active_urls)
        return homepage, 0, True

    return best_url, best_score, False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    active_urls = [u.strip() for u in data.get("active_urls", []) if u.strip()]
    redirect_urls = [u.strip() for u in data.get("redirect_urls", []) if u.strip()]

    if not active_urls or not redirect_urls:
        return jsonify({"error": "Her iki listeye de URL girmelisiniz."}), 400

    patterns = build_patterns(active_urls)

    results = []
    for rurl in redirect_urls:
        best_url, score, is_homepage = find_best_match(rurl, active_urls, patterns)
        results.append({
            "redirect_url": rurl,
            "target_url": best_url or "-",
            "score": score,
            "is_homepage": is_homepage,
        })

    return jsonify({"results": results})


@app.route("/export", methods=["POST"])
def export():
    data = request.get_json()
    results = data.get("results", [])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yönlendirmeler"

    # Başlıklar
    headers = ["404 URL (Yönlendirilecek)", "Hedef URL (Yönlenecek)", "Benzerlik Skoru"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = openpyxl.styles.Font(bold=True)

    # Veriler
    for i, row in enumerate(results, 2):
        ws.cell(row=i, column=1, value=row["redirect_url"])
        ws.cell(row=i, column=2, value=row["target_url"])
        ws.cell(row=i, column=3, value=row["score"])

    # Sütun genişlikleri
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 18

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()

    return send_file(
        tmp.name,
        as_attachment=True,
        download_name="yonlendirmeler.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5859)

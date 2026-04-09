from flask import Flask, render_template, request, jsonify, send_file
from urllib.parse import urlparse, unquote
from rapidfuzz import fuzz
import openpyxl
import tempfile
import os
import re

app = Flask(__name__)


def extract_keywords(url):
    """URL'den anlamlı anahtar kelimeleri çıkar."""
    parsed = urlparse(unquote(url))
    path = parsed.path.strip("/")

    # Uzantıları kaldır
    path = re.sub(r"\.(html?|php|aspx?|jsp)$", "", path, flags=re.IGNORECASE)

    # Ayırıcıları boşluğa çevir
    tokens = re.split(r"[-_/+.,]", path)

    # Boş ve çok kısa tokenları filtrele
    keywords = [t.lower() for t in tokens if len(t) > 1]
    return keywords


def score_match(source_url, target_url):
    """İki URL arasındaki benzerlik skorunu hesapla."""
    src_path = urlparse(unquote(source_url)).path.strip("/").lower()
    tgt_path = urlparse(unquote(target_url)).path.strip("/").lower()

    # 1) Tam yol eşleşmesi
    if src_path == tgt_path:
        return 100.0

    # 2) Fuzzy string benzerliği (yol bazlı)
    path_score = fuzz.token_sort_ratio(src_path, tgt_path)

    # 3) Anahtar kelime kesişimi
    src_kw = set(extract_keywords(source_url))
    tgt_kw = set(extract_keywords(target_url))

    if src_kw and tgt_kw:
        intersection = src_kw & tgt_kw
        union = src_kw | tgt_kw
        keyword_score = (len(intersection) / len(union)) * 100 if union else 0
    else:
        keyword_score = 0

    # Ağırlıklı ortalama
    final_score = (path_score * 0.6) + (keyword_score * 0.4)
    return round(final_score, 1)


def find_best_match(redirect_url, active_urls):
    """404 URL için en iyi eşleşen aktif URL'yi bul."""
    best_url = None
    best_score = 0

    for active_url in active_urls:
        score = score_match(redirect_url, active_url)
        if score > best_score:
            best_score = score
            best_url = active_url

    return best_url, best_score


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

    results = []
    for rurl in redirect_urls:
        best_url, score = find_best_match(rurl, active_urls)
        results.append({
            "redirect_url": rurl,
            "target_url": best_url or "-",
            "score": score,
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

from flask import Flask, render_template, request, jsonify, send_file
from urllib.parse import urlparse, unquote
from rapidfuzz import fuzz
import openpyxl
import tempfile
import os
import re

app = Flask(__name__)


def parse_url(url):
    """URL'yi parçalarına ayır: kategori, slug kelimeleri, tam path."""
    parsed = urlparse(unquote(url))
    path = parsed.path.strip("/").lower()
    path = re.sub(r"\.(html?|php|aspx?|jsp)$", "", path, flags=re.IGNORECASE)

    segments = [s for s in path.split("/") if s]
    category = segments[0] if segments else ""

    # Tüm segmentlerden anlamlı kelimeleri çıkar (3+ karakter)
    words = set()
    for seg in segments:
        for w in re.split(r"[-_+.,]", seg):
            if len(w) >= 3:
                words.add(w)

    return {
        "path": path,
        "category": category,
        "segments": segments,
        "words": words,
    }


def find_homepage(active_urls):
    """Aktif URL'ler arasından anasayfayı bul."""
    for url in active_urls:
        path = urlparse(url).path.strip("/")
        if not path or path in ("index", "index.html", "anasayfa", "home"):
            return url
    return min(active_urls, key=lambda u: len(urlparse(u).path.strip("/")))


def match_urls(redirect_url, active_urls, active_parsed_list):
    """404 URL için en uygun aktif URL'yi bul.

    Hiyerarşik eşleştirme:
      1) Tam path eşleşmesi → %100
      2) Aynı kategori + ortak kelime → yüksek skor
      3) Farklı kategori ama ortak kelime → orta skor
      4) Hiçbir ortak kelime yok → anasayfa
    """
    r = parse_url(redirect_url)

    # Tam path eşleşmesi
    for i, ap in enumerate(active_parsed_list):
        if r["path"] == ap["path"]:
            return active_urls[i], 100.0, False

    best_url = None
    best_score = 0.0

    for i, ap in enumerate(active_parsed_list):
        # Ortak kelimeleri bul (her iki URL'de de geçen 3+ karakterli kelimeler)
        common_words = r["words"] & ap["words"]
        if not common_words:
            continue

        # --- Kelime skoru ---
        # 404 URL'deki kelimelerin ne kadarı aktif URL'de var?
        r_coverage = len(common_words) / len(r["words"]) if r["words"] else 0
        # Aktif URL'deki kelimelerin ne kadarı 404 URL'de var?
        a_coverage = len(common_words) / len(ap["words"]) if ap["words"] else 0
        # İkisinin ortalaması
        word_score = ((r_coverage + a_coverage) / 2) * 50

        # --- Kategori skoru ---
        cat_score = 0
        if r["category"] and ap["category"] and r["category"] == ap["category"]:
            cat_score = 30  # Aynı kategori = büyük bonus

        # --- Slug benzerlik skoru (fuzzy) ---
        # Sadece son segment (asıl sayfa slug'ı) karşılaştır
        r_slug = r["segments"][-1] if r["segments"] else ""
        a_slug = ap["segments"][-1] if ap["segments"] else ""
        slug_fuzzy = fuzz.token_sort_ratio(r_slug, a_slug) * 0.20

        score = word_score + cat_score + slug_fuzzy

        if score > best_score:
            best_score = score
            best_url = active_urls[i]

    # Hiç ortak kelime bulamadıysa → anasayfa
    if best_url is None:
        return find_homepage(active_urls), 0, True

    return best_url, round(min(best_score, 100.0), 1), False


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

    active_parsed = [parse_url(u) for u in active_urls]

    results = []
    for rurl in redirect_urls:
        best_url, score, is_homepage = match_urls(rurl, active_urls, active_parsed)
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

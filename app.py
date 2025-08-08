import os
import asyncio
import random
from flask import Flask, request, render_template, send_file, session
import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Optional proxy list for rotation
PROXIES = [
    None,
    "http://51.158.154.173:3128",
    "http://185.199.229.156:7492",
    "http://51.81.32.81:8888"
]

# --- Static scraper ---
def scrape_static(url, selector):
    proxy = random.choice(PROXIES)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, proxies=proxies, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    elements = soup.select(selector)
    return [el.get_text(strip=True) for el in elements]

# --- JavaScript-rendered scraper ---
async def scrape_js(url, selector):
    proxy = random.choice(PROXIES)
    launch_args = {}
    if proxy:
        launch_args["proxy"] = {"server": proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url, timeout=45000)
        await page.wait_for_selector(selector, timeout=20000)
        elements = await page.query_selector_all(selector)
        data = [await el.inner_text() for el in elements]
        await browser.close()
        return data

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        selector = request.form.get("selector")
        mode = request.form.get("mode")

        try:
            if mode == "static":
                results = scrape_static(url, selector)
            else:
                results = asyncio.run(scrape_js(url, selector))

            df = pd.DataFrame(results, columns=["Result"])
            session["data"] = df.to_dict(orient="records")
            return render_template("results.html", data=results, url=url)

        except Exception as e:
            return render_template("index.html", error=str(e))

    return render_template("index.html")

@app.route("/download/<fmt>")
def download(fmt):
    data = session.get("data")
    if not data:
        return "No data to download", 400

    df = pd.DataFrame(data)
    output = BytesIO()
    if fmt == "csv":
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="results.csv", mimetype="text/csv")
    elif fmt == "json":
        df.to_json(output, orient="records")
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="results.json", mimetype="application/json")
    else:
        return "Invalid format", 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

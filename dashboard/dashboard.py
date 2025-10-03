from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import logging
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Web Scraper functions ---

def humanlike_scroll(driver):
    total_height = driver.execute_script("return document.body.scrollHeight")
    current_pos = 0
    while current_pos < total_height:
        scroll_amt = random.randint(200, 400)
        driver.execute_script(f"window.scrollBy(0, {scroll_amt})")
        current_pos += scroll_amt
        time.sleep(random.uniform(1.0, 3.5))

def safe_mouse_movement(driver):
    action = ActionChains(driver)
    try:
        width = driver.execute_script("return window.innerWidth")
        height = driver.execute_script("return window.innerHeight")
        for _ in range(random.randint(3, 7)):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            action.move_by_offset(x, y).perform()
            time.sleep(random.uniform(0.2, 1.0))
        body = driver.find_element_by_tag_name("body")
        action.move_to_element_with_offset(body, 0, 0).perform()
    except Exception as e:
        logger.warning(f"Mouse move error ignored: {e}")

def identify_job_cards_and_fields(soup):
    tags = soup.find_all(['li', 'div', 'article', 'section'])
    candidates = []
    for t in tags:
        children = t.find_all(True, recursive=False)
        if len(children) >= 2 and len(t.find_all(True, recursive=True)) > 30:
            candidates.append(t)
    if not candidates:
        return [], {}
    container_candidates = {}
    for c in candidates:
        parent = c.parent
        container_candidates[parent] = container_candidates.get(parent, 0) + 1
    main_container = max(container_candidates, key=container_candidates.get)
    job_cards = [child for child in main_container.find_all(True, recursive=False) if child.name in ['li','div','article','section']]
    return job_cards, {}

def extract_job_data(card):
    def get_text_or_default(tag):
        return tag.get_text(strip=True) if tag else "NA"
    job_title = get_text_or_default(card.find(['h1', 'h2', 'h3', 'a']))
    company_name = get_text_or_default(card.find(text=re.compile('company', re.IGNORECASE)))
    job_link = card.find('a')['href'] if card.find('a') else "NA"
    return {
        "job_title": job_title,
        "company_name": company_name,
        "job_link": job_link
    }

def selenium_dynamic_scraper(site_url):
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(options=options)
    jobs = []
    try:
        driver.get(site_url)
        time.sleep(5)
        humanlike_scroll(driver)
        safe_mouse_movement(driver)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards, _ = identify_job_cards_and_fields(soup)
        for card in job_cards:
            job_data = extract_job_data(card)
            jobs.append(job_data)
    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        driver.quit()
    return jobs

@app.route("/scrape-jobs", methods=["POST"])
def scrape_jobs():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    jobs = selenium_dynamic_scraper(url)
    return jsonify({"jobs": jobs})

# --- Email sender functions ---

SMTP_SERVER = "mail.a.trytalrn.com"
SMTP_PORT = 465
SMTP_USER = "hirea.trytalrn.com"
SMTP_PASS = "kAPYKh,5306sQ"  # Replace with secure storage in production!

@app.route("/send-email", methods=["POST"])
def send_email():
    data = request.get_json()
    recipients = data.get("recipients")
    subject = data.get("subject", "")
    emailbody = data.get("emailbody")
    replyto = data.get("replyto", None)
    cc = data.get("cc", None)
    bcc = data.get("bcc", None)

    if not recipients or not emailbody:
        return jsonify({"error": "Recipients and emailbody are required"}), 400

    recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
    cc_list = [c.strip() for c in cc.split(",")] if cc else []
    bcc_list = [b.strip() for b in bcc.split(",")] if bcc else []

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(recipient_list)
        if replyto:
            msg["Reply-To"] = replyto
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        if bcc_list:
            msg["Bcc"] = ", ".join(bcc_list)
        msg.set_content(emailbody)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Email sent successfully!"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

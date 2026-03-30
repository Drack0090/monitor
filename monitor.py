import os
import json
import time
import hashlib
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ── Configuración ──────────────────────────────────────────────
URL        = "https://continua.itla.edu.do/consultar-solicitudes"
CEDULA     = "40212955823"
WEBHOOK    = os.environ["ITLA_WEBHOOK"]
STATE_FILE = "last_state.json"
# ──────────────────────────────────────────────────────────────


def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=opts)


def scrape():
    driver = get_driver()
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 20)

        # Esperar el dropdown y seleccionar "Solicitud por Convocatoria de Becas"
        dropdown_el = wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "select"))
        )
        Select(dropdown_el).select_by_visible_text("Solicitud por Convocatoria de Becas")

        # Escribir la cédula
        input_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[placeholder*='identificaci']"))
        )
        input_el.clear()
        input_el.send_keys(CEDULA)

        # Click en Consultar
        btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Consultar')]"))
        )
        btn.click()

        # Esperar resultados (card o mensaje vacío)
        time.sleep(4)

        cards = driver.find_elements(By.CSS_SELECTOR, "div.bg-white, div[class*='card'], div[class*='solicitud']")

        solicitudes = []
        for card in cards:
            text = card.text.strip()
            if text and len(text) > 20:
                solicitudes.append(text)

        if not solicitudes:
            # Intentar capturar cualquier contenido relevante del body
            body = driver.find_element(By.TAG_NAME, "body").text
            return {"raw": body, "solicitudes": []}

        return {"solicitudes": solicitudes}

    finally:
        driver.quit()


def hash_state(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(serialized.encode()).hexdigest()


def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(data: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_discord(current: dict, previous: dict | None):
    if current.get("solicitudes"):
        description_lines = []
        for s in current["solicitudes"]:
            lines = s.splitlines()
            description_lines.append("\n".join(f"> {l}" for l in lines if l.strip()))
        description = "\n\n".join(description_lines)
    else:
        description = "No se encontraron solicitudes con los datos consultados."

    if previous is None:
        title  = "📋 Primera consulta registrada"
        color  = 0x3498db
    else:
        title  = "🔔 ¡Cambio detectado en tu solicitud ITLA!"
        color  = 0xe74c3c

    embed = {
        "title": title,
        "description": description[:3900],
        "color": color,
        "footer": {"text": f"Cédula: {CEDULA} • ITLA Continua"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    payload = {"embeds": [embed]}
    resp = requests.post(WEBHOOK, json=payload, timeout=15)
    resp.raise_for_status()
    print("✅ Notificación enviada a Discord.")


def main():
    print(f"🔍 Consultando estado de solicitud para cédula {CEDULA}...")
    current = scrape()
    print("Datos obtenidos:", json.dumps(current, ensure_ascii=False, indent=2)[:500])

    previous = load_last_state()

    current_hash  = hash_state(current)
    previous_hash = hash_state(previous) if previous else None

    if current_hash != previous_hash:
        print("⚡ Cambio detectado. Enviando notificación...")
        send_discord(current, previous)
        save_state(current)
    else:
        print("✔️  Sin cambios. No se envía notificación.")


if __name__ == "__main__":
    main()

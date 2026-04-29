# CarCOM

CarCOM egy Python alapú mikroservice architektúra, amely egy Google Sheets-ben vezetett jármű adminisztrációt dolgoz fel, validál és automatizál.

A rendszer célja, hogy a manuális pénzügyi és adminisztratív folyamatokat (jármű vásárlás, eladás) strukturált, ellenőrizhető és automatizálható formába alakítsa.

---

## 🚀 Fő funkciók (jelenlegi állapot)

### 📥 Adatfeldolgozás

* Google Sheets szinkronizáció
* Változáskövetés (versioning)
* Nyers adatréteg (raw storage)

### 🔄 Normalizálás

* Strukturált pénzügyi adatmodell (`finance_transactions`)
* Automatikus adattípus konverzió (dátum, pénz, stb.)
* Költséghely → tranzakció típus mapping

### ✅ Validáció

* Kötelező mezők ellenőrzése
* Üzleti szabály alapú validáció
* Hibák és figyelmeztetések külön tárolása

### 📎 Dokumentum kezelés

* Google Sheets szelvényekből link kinyerés
* Több fájl kezelése egy cellában
* Google Drive URL-ek tárolása

### 🌐 Web dashboard

* Tranzakció lista (szűrés, keresés, rendezés)
* Validációs hibák nézet
* Részletes tranzakció oldal
* Manuális szinkron indítás

---

## 🧠 Architektúra

```text
Google Sheet
    ↓
sync_service
    ↓
raw + versioned data
    ↓
processing layer
    ↓
finance_transactions (normalizált adatok)
    ↓
validation layer
    ↓
web_service (dashboard)
```

---

## 🏗️ Projekt struktúra

```text
services/
  main_service/        # Orchestration (pipeline)
  sync_service/        # Google Sheets integráció
  web_service/         # Web dashboard (FastAPI)
shared/
  database/            # DB connection + schema
```

---

## ⚙️ Telepítés

### 1. Repository klónozása

```bash
git clone https://github.com/NTibor13/CarCOM.git
cd CarCOM
```

---

### 2. Virtuális környezet

```bash
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
```

---

### 3. Függőségek telepítése

```bash
pip install -r requirements.txt
```

---

### 4. Környezeti változók

```bash
cp .env.example .env
```

Majd töltsd ki a `.env` fájlt.

---

### 5. Google Service Account

* Hozz létre egy Google Cloud Service Account-ot
* Töltsd le a `credentials.json` fájlt
* Helyezd el a projekt gyökérben
* Oszd meg a Google Sheet-et a service account e-mail címével

---

## ▶️ Futtatás

### Teljes pipeline futtatása

```bash
python -m services.main_service.app --pipeline
```

---

### Web felület indítása

```bash
python -m uvicorn services.web_service.app:app --reload
```

Böngésző:

```text
http://127.0.0.1:8000
```

---

## 📊 Dashboard funkciók

### Tranzakció lista

* 25 elem / oldal
* Google sor szerinti rendezés
* keresés (autó, ügyfél, ID)
* szűrés (típus, státusz)

### Validációs hibák

* hibák és figyelmeztetések listája
* mező + hibakód + üzenet

### Tranzakció részletek

* normalizált adatok
* validációs hibák
* dokumentumok
* raw Google Sheet adat

---

## 🔒 Biztonság

A repository **nem tartalmaz érzékeny adatokat**.

Kizárt fájlok:

* `.env`
* `credentials.json`
* `data/*.db`
* `.venv/`

---

## 🧭 Roadmap

### Rövid táv

* UI finomítás
* Sync státusz megjelenítés
* Tranzakció kiemelések (ERROR / WARNING)

### Közép táv

* Flow engine (vásárlás / eladás automatizmus)
* Billingo integráció
* Banki integráció (MBH)

### Hosszú táv

* AI dokumentum feldolgozás
* OCR + adatellenőrzés
* Automatizált validáció dokumentumok alapján

---

## 🤖 AI irány (jövő)

A rendszer már tartalmazza:

```text
transaction → document → file_url
```

Ez lehetővé teszi:

* dokumentum letöltést
* OCR feldolgozást
* AI alapú adatellenőrzést

---

## 📄 Licenc

Private project – belső használatra.

---

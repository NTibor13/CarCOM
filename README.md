# CarCOM v1

Első futtatható alkalmazásverzió Python alapon.

## Indítás

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m services.main_service.app --once
```

## Időzített futtatás

```bash
python -m services.main_service.app --scheduler
```

## Google Sheets jogosultság

A `credentials.json` service account kulcsfájlt a projekt gyökerébe kell tenni, és a Google Sheet-et meg kell osztani a service account email címével olvasási jogosultsággal.

EXPECTED_FINANCE_HEADERS = [
    "ID",
    "Datum",
    "Számla",
    "Osszeg (brutto)",
    "Afa %",
    "Osszeg (netto)",
    "Koltseghely",
    "Autó",
    "Hónap",
    "ÉV",
    "Ügyfél",
    "Bankszámlaszám",
    "Közlemény",
    "Fizetési határidő",
    "Eredeti számla",
    "Bejövő Advét/Számla",
    "Felkészítés",
    "Bizonylat / sztornó link",
    "Számla link",
    "Advét link",
    "Eladás advét Nf office",
    "Bizomány elszámló",
    "Státusz Számla",
    "Státusz fizetés",
    "KG tartozik",
    "Megjegyzés",
    # Jelenleg a forrásban szereplő extra, pénzügyi segédoszlopok.
    "EUR (brutto)",
    "EUR (netto)",
    "EUR HUF ban",
    "Váltás árfolyam",
    "Összesen nettó forintban",
]

SOURCE_ACCOUNT_VALUES = {
    "Egyenleg",
}

VAT_RATE_MAP = {
    "0%": "0",
    "18%": "0.18",
    "27%": "0.27",
}

KOLTSEGHELY_MAP = {
    "Vétel": "PURCHASE",
    "Eladás": "SALE",
    "Eladás készlet 90 nap": "SALE_STOCK_90_DAYS",
    "Adminisztráció": "OTHER",
    "Egyéb": "OTHER",
    "Foglaló": "OTHER",
    "Felkészítés": "OTHER",
    "Bizományos értékesítés": "OTHER",
}

INVOICE_STATUS_VALUES = {
    "",
    "Számlára vár",
    "Számlázott",
}

PAYMENT_STATUS_VALUES = {
    "",
    "Fizetésre vár (vétel)",
    "Fizetett (vétel)",
    "Részben fizetett (vétel)",
    "Kiegyenlítésre vár (eladás)",
    "Kiegyenlített (eladás)",
    "Részben kiegyenlített (eladás)",
}

DOCUMENT_COLUMNS = {
    "Számla link": "INVOICE",
    "Advét link": "SALE_PURCHASE_CONTRACT",
}

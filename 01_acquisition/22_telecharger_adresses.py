# 22_telecharger_adresses.py
# Télécharge les adresses UrbIS (WFS urbisvector:Addresses) SANS la géométrie (les coordonnées sont dans
# XL72 / YL72, en Lambert 72) et seulement les attributs utiles, par pages de 100 000, triées par
# identifiant pour que la pagination soit stable. Enregistre un CSV TEL QUEL + la trace de la requête.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\22_telecharger_adresses.py

import sys
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

URL_WFS = "https://geoservices-urbis.irisnet.be/geoserver/urbisvector/wfs"
COUCHE = "urbisvector:Addresses"
ATTRIBUTS = ["INSPIRE_ID", "POLICENUM", "BOXNUMBER", "PARENTID", "STATNISCODE", "BU_ID", "CAPAKEY", "XL72", "YL72"]
PAGE = 100_000
DOSSIER = config.DATA_BRUT / "urbis_adresses"
FICHIER = DOSSIER / f"urbis_adresses_{date.today():%Y%m%d}.csv"
FICHIER_REQUETE = DOSSIER / "urbis_adresses_requete.txt"
BASE = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": COUCHE}


def get(params):
    r = requests.get(URL_WFS, params={**BASE, **params}, timeout=600)
    if r.status_code != 200:
        sys.exit(f"FAIL  HTTP {r.status_code} : {r.text[:300]}")
    return r


# --- 1. Combien d'adresses le serveur annonce-t-il ? ---
annonce = int(re.search(r'numberMatched="(\d+)"', get({"resultType": "hits"}).text).group(1))
print(f"INFO  {annonce} adresses annoncées par le serveur")

# --- 2. Téléchargement page par page ---
pages, debut = [], 0
while debut < annonce:      # on avance du nombre RÉELLEMENT reçu (le serveur peut plafonner les pages)
    r = get({"propertyName": ",".join(ATTRIBUTS), "outputFormat": "application/json",
             "sortBy": "INSPIRE_ID", "startIndex": debut, "count": PAGE})
    try:
        donnees = json.loads(r.text)
    except json.JSONDecodeError:
        sys.exit(f"FAIL  page {debut} : la réponse n'est pas du GeoJSON ; début : {r.text[:300]}")
    lignes = [f["properties"] for f in donnees["features"]]
    if not lignes:
        sys.exit(f"FAIL  page vide à partir de {debut} : rien n'est enregistré")
    pages.append(pd.DataFrame(lignes, columns=ATTRIBUTS))
    print(f"INFO  page à partir de {debut} : {len(lignes)} adresses")
    debut += len(lignes)

adresses = pd.concat(pages, ignore_index=True)

# --- 3. Contrôles de complétude (avant d'enregistrer) ---
ok_nombre = len(adresses) == annonce
print(f"{'PASS' if ok_nombre else 'FAIL'}  {len(adresses)} reçues pour {annonce} annoncées")
doublons = adresses["INSPIRE_ID"].duplicated().sum()
print(f"{'PASS' if doublons == 0 else 'FAIL'}  identifiants en double : {doublons} (pagination stable si 0)")
if not ok_nombre or doublons:
    sys.exit("Arrêt : rien n'est enregistré")

# --- 4. Enregistrement tel quel + trace ---
DOSSIER.mkdir(parents=True, exist_ok=True)
adresses.to_csv(FICHIER, index=False, encoding="utf-8")     # CSV standard (virgule) : fichier brut
FICHIER_REQUETE.write_text(
    f"Source   : UrbIS – Adresses (Paradigm), WFS {URL_WFS}\n"
    f"Couche   : {COUCHE}\n"
    f"Attributs: {', '.join(ATTRIBUTS)} (sans géométrie : XL72/YL72 en EPSG:31370)\n"
    f"Pages    : {PAGE} objets, triés par INSPIRE_ID\n"
    f"Date     : {date.today().isoformat()}\n"
    f"Adresses : {len(adresses)}\n",
    encoding="utf-8",
)
print(f"PASS  enregistré : {FICHIER.relative_to(RACINE)} ({FICHIER.stat().st_size / 1e6:.0f} Mo)")

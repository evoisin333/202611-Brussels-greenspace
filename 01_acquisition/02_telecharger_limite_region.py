# 02_telecharger_limite_region.py
# Télécharge le contour de la Région de Bruxelles-Capitale depuis le WFS UrbIS (Paradigm).
# Le fichier est enregistré TEL QUEL (aucune modification) dans data/brut/<ville>/.
# La requête exacte et la date sont écrites dans un petit fichier texte à côté.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\02_telecharger_limite_region.py

import sys
import json
from datetime import date
from pathlib import Path

import requests
from owslib.wfs import WebFeatureService

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

URL_WFS = "https://geoservices-urbis.irisnet.be/geoserver/urbisvector/wfs"
COUCHE = "urbisvector:Region"
CRS = "EPSG:31370"   # Lambert 72, CRS natif des données UrbIS
FICHIER = config.DATA_BRUT / "urbis_region.geojson"
FICHIER_REQUETE = config.DATA_BRUT / "urbis_region_requete.txt"

print("--- Requête ---")
print(f"Service : {URL_WFS}")
print(f"Couche  : {COUCHE}")
print(f"CRS     : {CRS}")
print(f"Date    : {date.today().isoformat()}")

# --- 1. La couche existe-t-elle dans le service ? ---
try:
    wfs = WebFeatureService(URL_WFS, version="2.0.0", timeout=60)
except Exception as erreur:
    print(f"FAIL  service WFS injoignable ({erreur})")
    sys.exit(1)

couches = list(wfs.contents)
print(f"\nINFO  {len(couches)} couches dans le service")
if COUCHE not in couches:
    candidates = [c for c in couches if "region" in c.lower()]
    print(f"FAIL  couche {COUCHE} absente. Couches contenant 'region' : {candidates}")
    sys.exit(1)
print(f"PASS  couche {COUCHE} trouvée")

# --- 2. Téléchargement (GetFeature, GeoJSON) ---
parametres = {
    "service": "WFS",
    "version": "2.0.0",
    "request": "GetFeature",
    "typeNames": COUCHE,
    "outputFormat": "application/json",
    "srsName": CRS,
}
reponse = requests.get(URL_WFS, params=parametres, timeout=120)
if reponse.status_code != 200:
    print(f"FAIL  téléchargement refusé (code HTTP {reponse.status_code})")
    sys.exit(1)

# On vérifie que la réponse est bien du GeoJSON et pas un message d'erreur du serveur
try:
    contenu = json.loads(reponse.text)
except json.JSONDecodeError:
    print("FAIL  la réponse n'est pas du GeoJSON. Début de la réponse :")
    print(reponse.text[:500])
    sys.exit(1)
n_entites = len(contenu.get("features", []))
print(f"PASS  réponse GeoJSON reçue ({n_entites} entité(s))")

# --- 3. Enregistrement tel quel + trace de la requête ---
config.DATA_BRUT.mkdir(parents=True, exist_ok=True)
FICHIER.write_bytes(reponse.content)
FICHIER_REQUETE.write_text(
    f"URL exacte : {reponse.url}\n"
    f"Date de téléchargement : {date.today().isoformat()}\n"
    f"Source : UrbIS (Paradigm), couche {COUCHE}\n",
    encoding="utf-8",
)
print(f"\nFichier écrit : {FICHIER.relative_to(RACINE)} ({len(reponse.content) / 1024:.0f} Ko)")
print(f"Requête notée : {FICHIER_REQUETE.relative_to(RACINE)}")
print("\nÉtape suivante : python 00_audit\\03_verif_limite_region.py")

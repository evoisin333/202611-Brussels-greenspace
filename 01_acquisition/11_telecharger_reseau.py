# 11_telecharger_reseau.py
# Étape 1.7 : télécharge le réseau de voies (OpenStreetMap, via l'API Overpass, figé à une date)
# et les axes de rues UrbIS (référence officielle pour contrôler la couverture d'OSM).
# Emprise : Région + 500 m (un trajet vers un parc peut passer brièvement par la Flandre).
# Fichiers enregistrés TELS QUELS. Licence OSM : ODbL, « © OpenStreetMap contributors ».
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\11_telecharger_reseau.py

import re
import sys
import json
import time
from datetime import date
from pathlib import Path

import requests
import geopandas as gpd
from owslib.wfs import WebFeatureService

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

MARGE_M = 500
DATE_OSM = "2026-11-01T00:00:00Z"            # date fixe : les données OSM telles qu'elles étaient ce jour-là
URL_OVERPASS = "https://overpass-api.de/api/interpreter"
URL_URBIS = "https://geoservices-urbis.irisnet.be/geoserver/urbisvector/wfs"
CRS = "EPSG:31370"
DOSSIER = config.DATA_BRUT / "reseau"
FICHIER_OSM = DOSSIER / "osm_highway_20261101.json"
FICHIER_URBIS = DOSSIER / "urbis_axes_rues.geojson"
FICHIER_REQUETE = DOSSIER / "requetes_reseau.txt"
ENTETES = {"User-Agent": "Brussels-greenspace portfolio project (reproducible audit script)"}

DOSSIER.mkdir(parents=True, exist_ok=True)

# --- 1. Emprise : Région + 500 m, en WGS84 pour Overpass ---
region = gpd.read_file(config.DATA_BRUT / "urbis_region.geojson").to_crs(31370)
emprise = region.buffer(MARGE_M).to_crs(4326).total_bounds   # lon_min, lat_min, lon_max, lat_max
sud, ouest, nord, est = emprise[1], emprise[0], emprise[3], emprise[2]
print(f"--- Emprise (Région + {MARGE_M} m, WGS84) : S {sud:.5f}, O {ouest:.5f}, N {nord:.5f}, E {est:.5f}")

# --- 2. OpenStreetMap : toutes les voies (highway=*), avec identifiants des nœuds et géométrie ---
# Requête découpée en 2 x 2 tuiles (plus légères pour le serveur), avec plusieurs essais si Overpass est saturé.
print("\n--- OpenStreetMap (Overpass) ---")
N_TUILES = 2            # 2 x 2 = 4 tuiles
ESSAIS, ATTENTE_S = 3, 60


def requete_tuile(s, o, n, e):
    """Texte de la requête Overpass pour une tuile (date figée, mémoire par défaut du serveur)."""
    return (f'[out:json][timeout:300][date:"{DATE_OSM}"];\n'
            f'way["highway"]({s:.6f},{o:.6f},{n:.6f},{e:.6f});\n'
            'out body geom;')


lats = [sud + i * (nord - sud) / N_TUILES for i in range(N_TUILES + 1)]
lons = [ouest + j * (est - ouest) / N_TUILES for j in range(N_TUILES + 1)]
requetes_osm = []
voies_par_id = {}
for i in range(N_TUILES):
    for j in range(N_TUILES):
        texte = requete_tuile(lats[i], lons[j], lats[i + 1], lons[j + 1])
        requetes_osm.append(texte)
        fichier_tuile = DOSSIER / f"osm_highway_20261101_tuile_{i}{j}.json"
        if not fichier_tuile.exists():
            for essai in range(1, ESSAIS + 1):
                reponse = requests.post(URL_OVERPASS, data={"data": texte}, headers=ENTETES, timeout=600)
                if reponse.status_code == 200:
                    fichier_tuile.write_bytes(reponse.content)
                    break
                print(f"INFO  tuile {i}{j}, essai {essai}/{ESSAIS} : code HTTP {reponse.status_code} (serveur saturé ?)")
                if essai < ESSAIS:
                    time.sleep(ATTENTE_S)
            else:
                print(f"FAIL  tuile {i}{j} refusée après {ESSAIS} essais : réessayer plus tard "
                      "(les tuiles déjà reçues sont gardées)")
                sys.exit(1)
        contenu = json.loads(fichier_tuile.read_text(encoding="utf-8"))
        if "remark" in contenu:     # Overpass signale ici un dépassement de temps ou de mémoire
            print(f"FAIL  tuile {i}{j} incomplète : {contenu['remark']} (supprimer le fichier et relancer)")
            sys.exit(1)
        voies_tuile = [e for e in contenu.get("elements", []) if e.get("type") == "way"]
        for v in voies_tuile:
            voies_par_id[v["id"]] = v      # une voie à cheval sur deux tuiles n'est gardée qu'une fois
        print(f"PASS  tuile {i}{j} : {len(voies_tuile)} voies")
        etat_osm = contenu.get("osm3s", {}).get("timestamp_osm_base", "non indiqué")

voies = list(voies_par_id.values())
FICHIER_OSM.write_text(json.dumps({"osm3s": {"timestamp_osm_base": etat_osm, "date_requete": DATE_OSM},
                                   "elements": voies}), encoding="utf-8")
requete_osm = "\n".join(requetes_osm)
print(f"PASS  {len(voies)} voies OSM après fusion des tuiles ({FICHIER_OSM.stat().st_size / 1e6:.0f} Mo)")
print(f"INFO  état des données OSM : {etat_osm} (requête datée du {DATE_OSM})")

# --- 3. UrbIS : axes de rues (WFS) ---
print("\n--- UrbIS : axes de rues ---")
wfs = WebFeatureService(URL_URBIS, version="2.0.0", timeout=60)
couches = list(wfs.contents)
candidates = [c for c in couches if "street" in c.lower() and "ax" in c.lower()]
print(f"INFO  couches contenant « street » et « ax » : {candidates}")
if not candidates:
    print(f"FAIL  aucune couche d'axes de rues trouvée. Couches du service : {couches}")
    sys.exit(1)
couche = sorted(candidates, key=len)[0]   # le nom le plus court (pas une variante « NamesFr »…)
print(f"PASS  couche retenue : {couche}")


def get_feature(**autres):
    """Requête GetFeature WFS 2.0 sur la couche d'axes."""
    parametres = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": couche, **autres}
    return requests.get(URL_URBIS, params=parametres, timeout=600)


trouve = re.search(r'numberMatched="(\d+)"', get_feature(resultType="hits").text)
annonce = int(trouve.group(1)) if trouve else None
premiere = get_feature(outputFormat="application/json", srsName=CRS)
entites = json.loads(premiere.text).get("features", [])
if annonce is not None and len(entites) < annonce:      # réponse tronquée : pagination
    taille, entites = len(entites), []
    while len(entites) < annonce:
        page = json.loads(get_feature(outputFormat="application/json", srsName=CRS,
                                      count=taille, startIndex=len(entites)).text).get("features", [])
        if not page:
            break
        entites.extend(page)
if annonce is None:
    print(f"INFO  nombre total non annoncé ; {len(entites)} axes reçus")
elif len(entites) == annonce:
    print(f"PASS  {len(entites)} axes reçus = {annonce} annoncés")
else:
    print(f"FAIL  {len(entites)} axes reçus pour {annonce} annoncés")
    sys.exit(1)
collection = {"type": "FeatureCollection", "features": entites,
              "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::31370"}}}
FICHIER_URBIS.write_text(json.dumps(collection), encoding="utf-8")
print(f"Fichier écrit : {FICHIER_URBIS.relative_to(RACINE)} ({FICHIER_URBIS.stat().st_size / 1e6:.1f} Mo)")

FICHIER_REQUETE.write_text(
    f"Date de téléchargement : {date.today().isoformat()}\n"
    f"OSM (ODbL, © OpenStreetMap contributors) via {URL_OVERPASS}, requête :\n{requete_osm}\n"
    f"UrbIS : {URL_URBIS}, couche {couche}, {len(entites)} axes, CRS {CRS}\n", encoding="utf-8")
print(f"\nRequêtes notées : {FICHIER_REQUETE.relative_to(RACINE)}")
print("Étape suivante : python 00_audit\\12_verif_reseau.py")

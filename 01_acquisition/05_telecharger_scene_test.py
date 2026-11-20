# 05_telecharger_scene_test.py
# Étape 1.4 : télécharge UN passage test (toutes les bandes utiles), découpé sur la Région, SANS transformation.
# Bandes : lwir11 (ST_B10), qa (ST_QA), cdist (ST_CDIST), qa_pixel, red, nir08.
# Écrit dans data/brut/<ville>/landsat_test/ : un GeoTIFF par scène et par bande + la fiche STAC de chaque scène.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\05_telecharger_scene_test.py

import sys
import json
from datetime import date
from pathlib import Path

import pandas as pd
import geopandas as gpd
import rasterio
import rioxarray
import pystac_client
import planetary_computer

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

DATE_TEST = "2025-07-13"   # passage test : 99,99 % de la Région claire (audit 04)
ORBITE_TEST = "198"
BANDES = ["lwir11", "qa", "cdist", "qa_pixel", "red", "nir08"]

URL_CATALOGUE = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
CRS_UTM = "EPSG:32631"
MARGE = 60  # m autour de la Région
DOSSIER = config.DATA_BRUT / "landsat_test"

print("--- Requête ---")
print(f"Passage : {DATE_TEST}, orbite {ORBITE_TEST} ; bandes : {BANDES}")
print(f"Date    : {date.today().isoformat()}")

# --- 1. Scènes du passage (depuis le CSV de l'audit 01) ---
scenes = pd.read_csv(config.AUDIT / "01_landsat_catalogue.csv", sep=";", decimal=",",
                     dtype={"id": str, "wrs_path": str, "wrs_row": str})
ids = scenes[(scenes["date"] == DATE_TEST) & (scenes["wrs_path"] == ORBITE_TEST)]["id"].tolist()
print(f"\nINFO  scènes du passage : {ids}")
if not ids:
    print("FAIL  aucune scène pour ce passage dans 01_landsat_catalogue.csv")
    sys.exit(1)

# --- 2. Emprise de découpe (Région + marge, en UTM 31N) ---
region = gpd.read_file(config.DATA_BRUT / "urbis_region.geojson").to_crs(CRS_UTM)
xmin, ymin, xmax, ymax = region.total_bounds
boite = (xmin - MARGE, ymin - MARGE, xmax + MARGE, ymax + MARGE)

# --- 3. Téléchargement ---
catalogue = pystac_client.Client.open(URL_CATALOGUE)
items = list(catalogue.search(collections=[COLLECTION], ids=ids).items())
if len(items) != len(ids):
    print(f"FAIL  {len(items)} / {len(ids)} scènes retrouvées dans le catalogue")
    sys.exit(1)

# Toutes les bandes demandées existent-elles dans chaque fiche ?
for item in items:
    manquantes = [b for b in BANDES if b not in item.assets]
    if manquantes:
        print(f"FAIL  {item.id} : bandes absentes {manquantes}. Bandes disponibles : {sorted(item.assets)}")
        sys.exit(1)
print("PASS  les 6 bandes existent dans chaque scène")
DOSSIER.mkdir(parents=True, exist_ok=True)

with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2"):
    for item in items:
        # Fiche STAC complète (facteurs d'échelle, nodata, résolution...) : sert au contrôle 06
        (DOSSIER / f"{item.id}_stac.json").write_text(json.dumps(item.to_dict(), indent=1), encoding="utf-8")
        for bande in BANDES:
            href = planetary_computer.sign(item.assets[bande].href)     # lien signé, gratuit
            da = rioxarray.open_rasterio(href)
            fenetre = da.rio.clip_box(*boite, crs=CRS_UTM)               # découpe seulement, valeurs inchangées
            fichier = DOSSIER / f"{item.id}_{bande}.tif"
            fenetre.rio.to_raster(fichier, compress="deflate")
            print(f"  {fichier.name} : {fenetre.shape[-1]} x {fenetre.shape[-2]} px, nodata = {da.rio.nodata}")

n_tif = len(list(DOSSIER.glob("*.tif")))
attendu = len(items) * len(BANDES)
print(f"\n{'PASS' if n_tif == attendu else 'FAIL'}  {n_tif} / {attendu} fichiers écrits dans {DOSSIER.relative_to(RACINE)}")
print("\nÉtape suivante : python 00_audit\\06_verif_scene_test.py")

# 04_audit_landsat_part_claire.py
# Audit étape 1.3 : part de la Région observée et claire, PASSAGE par passage (même date + même orbite),
# pour les étés de config.ANNEES. Lit UNIQUEMENT la bande QA_PIXEL, sur la fenêtre de Bruxelles.
# Critère GO (fixé avant les données) : au moins 10 passages avec au moins 90 % de la Région observée et claire.
# Écrit une seule table : data/travail/<ville>/audit/04_part_claire_passages.csv (format français : ; et ,)
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\04_audit_landsat_part_claire.py
# Durée : environ 5 à 15 minutes selon la connexion.

import sys
import math
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rioxarray
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rioxarray.exceptions import NoDataInBounds
import pystac_client
import planetary_computer

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

URL_CATALOGUE = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
FICHIER_SCENES = config.AUDIT / "01_landsat_catalogue.csv"
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"
FICHIER_SORTIE = config.AUDIT / "04_part_claire_passages.csv"

CRS_UTM = "EPSG:32631"     # UTM 31N, grille des scènes Landsat sur Bruxelles
TAILLE_PIXEL = 30          # m
SEUIL_CLAIR = 90           # % de la Région observée ET claire
N_PASSAGES_MIN = 10        # critère GO

# QA_PIXEL Landsat 8-9 (USGS) : bit 0 Fill, 1 Dilated Cloud, 2 Cirrus, 3 Cloud, 4 Cloud Shadow
MASQUE_REMPLISSAGE = 1 << 0
MASQUE_NON_CLAIR = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)
VALEUR_REMPLISSAGE = 1     # valeur nodata de QA_PIXEL (bit Fill seul)

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


# --- 1. Entrées ---
print("--- Entrées ---")
if not FICHIER_SCENES.exists() or not FICHIER_REGION.exists():
    print("FAIL  lancer d'abord les scripts 01 (catalogue) et 02 (contour régional)")
    sys.exit(1)
scenes = pd.read_csv(FICHIER_SCENES, sep=";", decimal=",", dtype={"id": str, "wrs_path": str, "wrs_row": str})
scenes = scenes[scenes["annee"].isin(config.ANNEES)].copy()
print(f"INFO  {len(scenes)} scènes Landsat 8/9 en {config.ANNEES[0]}-{config.ANNEES[-1]}")

region = gpd.read_file(FICHIER_REGION).to_crs(CRS_UTM)
geom_region = region.geometry.union_all()

# --- 2. Récupération des liens vers QA_PIXEL ---
catalogue = pystac_client.Client.open(URL_CATALOGUE)
items = {}
ids = scenes["id"].tolist()
for debut in range(0, len(ids), 100):   # par paquets de 100 identifiants
    for item in catalogue.search(collections=[COLLECTION], ids=ids[debut:debut + 100]).items():
        items[item.id] = item
note(len(items) == len(scenes), f"{len(items)} / {len(scenes)} scènes retrouvées dans le catalogue")


def lire_qa(item_id, boite):
    """Lit QA_PIXEL d'une scène sur une boîte (xmin, ymin, xmax, ymax) en UTM 31N. Renvoie un DataArray ou None."""
    href = planetary_computer.sign(items[item_id].assets["qa_pixel"].href)   # lien signé, gratuit
    qa = rioxarray.open_rasterio(href).squeeze("band", drop=True)
    crs_scene = qa.rio.crs.to_string()
    try:
        fenetre = qa.rio.clip_box(*boite, crs=CRS_UTM)                     # ne lit que la fenêtre
    except NoDataInBounds:
        return None, crs_scene
    return fenetre.rio.write_nodata(VALEUR_REMPLISSAGE), crs_scene


# --- 3. Grille de référence alignée sur les pixels Landsat ---
# On cale la grille sur l'origine de la première scène : les scènes d'une même zone UTM partagent la même grille.
xmin, ymin, xmax, ymax = geom_region.bounds
marge = 2 * TAILLE_PIXEL
boite = (xmin - marge, ymin - marge, xmax + marge, ymax + marge)
premiere, _ = lire_qa(ids[0], boite)
x0 = float(premiere.rio.transform().c)
y0 = float(premiere.rio.transform().f)
gx_min = x0 + math.floor((xmin - x0) / TAILLE_PIXEL) * TAILLE_PIXEL
gy_max = y0 + math.ceil((ymax - y0) / TAILLE_PIXEL) * TAILLE_PIXEL
largeur = math.ceil((xmax - gx_min) / TAILLE_PIXEL)
hauteur = math.ceil((gy_max - ymin) / TAILLE_PIXEL)
transform = from_origin(gx_min, gy_max, TAILLE_PIXEL, TAILLE_PIXEL)
dans_region = geometry_mask([geom_region], out_shape=(hauteur, largeur), transform=transform, invert=True)
n_region = int(dans_region.sum())

print("\n--- Grille ---")
print(f"INFO  grille {largeur} x {hauteur} pixels de {TAILLE_PIXEL} m, {n_region:,} pixels dans la Région")
n_attendu = region.area.sum() / TAILLE_PIXEL ** 2
note(abs(n_region - n_attendu) / n_attendu < 0.02,
     f"nombre de pixels de la Région cohérent avec sa surface ({n_attendu:,.0f} attendus, écart < 2 %)")

# --- 4. Calcul passage par passage ---
print("\n--- Passages (date, orbite : scènes, % observé, % clair) ---")
scenes["passage"] = scenes["date"] + "_" + scenes["wrs_path"]
lignes, erreurs, crs_vus = [], [], set()

with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2"):
    for passage, groupe in scenes.groupby("passage"):
        observe = {"tout": np.zeros((hauteur, largeur), bool), "T1": np.zeros((hauteur, largeur), bool)}
        clair = {"tout": np.zeros((hauteur, largeur), bool), "T1": np.zeros((hauteur, largeur), bool)}
        n_t1 = 0
        for _, scene in groupe.iterrows():
            try:
                fenetre, crs_scene = lire_qa(scene["id"], boite)
                crs_vus.add(crs_scene)
                if fenetre is None:
                    continue
                # Remise sur la grille de référence (plus proche voisin : aucune valeur inventée)
                qa = fenetre.rio.reproject(CRS_UTM, shape=(hauteur, largeur), transform=transform,
                                           resampling=Resampling.nearest, nodata=VALEUR_REMPLISSAGE).values
            except Exception as erreur:
                erreurs.append(f"{scene['id']} : {erreur}")
                continue
            obs = (qa & MASQUE_REMPLISSAGE) == 0
            clr = obs & ((qa & MASQUE_NON_CLAIR) == 0)
            observe["tout"] |= obs
            clair["tout"] |= clr
            if scene["categorie"] == "T1":
                n_t1 += 1
                observe["T1"] |= obs
                clair["T1"] |= clr

        def pct(masque):
            return 100 * (masque & dans_region).sum() / n_region

        ligne = {
            "passage": passage,
            "date": groupe["date"].iloc[0],
            "annee": int(groupe["annee"].iloc[0]),
            "wrs_path": groupe["wrs_path"].iloc[0],
            "satellite": groupe["satellite"].iloc[0],
            "n_scenes": len(groupe),
            "n_scenes_T1": n_t1,
            "scenes": " ".join(groupe["id"]),
            "pct_observee": round(pct(observe["tout"]), 2),
            "pct_claire": round(pct(clair["tout"]), 2),
            "pct_observee_T1": round(pct(observe["T1"]), 2) if n_t1 else np.nan,
            "pct_claire_T1": round(pct(clair["T1"]), 2) if n_t1 else np.nan,
        }
        lignes.append(ligne)
        print(f"  {ligne['date']} orbite {ligne['wrs_path']} : {ligne['n_scenes']} scène(s), "
              f"{ligne['pct_observee']:5.1f} % observé, {ligne['pct_claire']:5.1f} % clair")

df = pd.DataFrame(lignes)

# --- 5. Contrôles ---
print("\n--- Contrôles ---")
note(len(erreurs) == 0, f"toutes les scènes lues ({len(erreurs)} erreurs)")
for e in erreurs[:10]:
    print(f"      {e}")
note(crs_vus == {CRS_UTM}, f"CRS des scènes : {sorted(crs_vus)} (attendu : {CRS_UTM} seul)")
note(df["pct_observee"].between(0, 100).all() and df["pct_claire"].between(0, 100).all(), "pourcentages entre 0 et 100")
note((df["pct_claire"] <= df["pct_observee"]).all(), "part claire toujours ≤ part observée")
note(df["pct_observee"].max() > 99, f"au moins un passage voit toute la Région (max {df['pct_observee'].max():.1f} %)")

# --- 6. Récapitulatifs ---
df["go_tout"] = df["pct_claire"] >= SEUIL_CLAIR
df["go_T1"] = df["pct_claire_T1"] >= SEUIL_CLAIR
print(f"\n--- Passages par année (clairs = au moins {SEUIL_CLAIR} % de la Région observée et claire) ---")
recap = df.groupby("annee").agg(passages=("passage", "count"),
                                clairs_T1_T2=("go_tout", "sum"),
                                clairs_T1=("go_T1", "sum"),
                                mediane_pct_claire=("pct_claire", "median"))
recap.loc["total"] = [recap["passages"].sum(), recap["clairs_T1_T2"].sum(), recap["clairs_T1"].sum(), df["pct_claire"].median()]
print(recap.round(1).to_string())

print("\n--- Distribution de la part claire (tous passages) ---")
classes = pd.cut(df["pct_claire"], bins=[-0.1, 10, 25, 50, 75, 90, 100],
                 labels=["0-10 %", "10-25 %", "25-50 %", "50-75 %", "75-90 %", "90-100 %"])
print(classes.value_counts().sort_index().to_string())

print("\n--- Passages clairs (T1 + T2) ---")
print(df[df["go_tout"]][["date", "wrs_path", "satellite", "pct_claire", "pct_claire_T1"]].to_string(index=False))

# --- 7. Verdict ---
n_go_tout, n_go_t1 = int(df["go_tout"].sum()), int(df["go_T1"].sum())
print("\n--- Verdict ---")
print(f"{'GO' if n_go_tout >= N_PASSAGES_MIN else 'NO-GO'}  T1 + T2 : {n_go_tout} passages clairs (minimum {N_PASSAGES_MIN})")
print(f"{'GO' if n_go_t1 >= N_PASSAGES_MIN else 'NO-GO'}  T1 seul : {n_go_t1} passages clairs (minimum {N_PASSAGES_MIN})")

# --- 8. Écriture ---
df.drop(columns=["go_tout", "go_T1"]).to_csv(FICHIER_SORTIE, sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(f"\nTable écrite : {FICHIER_SORTIE.relative_to(RACINE)}")
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

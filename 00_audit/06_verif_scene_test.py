# 06_verif_scene_test.py
# Contrôle en LECTURE SEULE du passage test téléchargé par 01_acquisition/05_telecharger_scene_test.py
# Critères fixés avant de voir les données (journal, 18/11/2026) :
#   - facteurs d'échelle des métadonnées = ceux de la passation (ST : 0,00341802 et 149,0 ; SR : 0,0000275 et -0,2)
#   - LST d'un jour clair de juillet : médiane de la Région entre 20 et 45 °C, 1er et 99e centiles entre 5 et 65 °C
#   - trous d'émissivité (pixels clairs sans température) ≤ 1 % de la Région
#   - NDVI dans [-1, 1] pour ≥ 99,9 % des pixels, médiane de la Région entre 0,3 et 0,6
#   - bon sens : la forêt de Soignes est plus froide que le centre-ville (Pentagone)
# Seule écriture : un aperçu PNG dans data/travail/<ville>/audit/ pour le contrôle visuel.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\06_verif_scene_test.py

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rioxarray
from rioxarray.merge import merge_arrays
from rasterio.features import geometry_mask
from shapely.geometry import box
import matplotlib
matplotlib.use("Agg")   # pas de fenêtre : on écrit seulement un fichier image
import matplotlib.pyplot as plt

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

DOSSIER = config.DATA_BRUT / "landsat_test"
FICHIER_APERCU = config.AUDIT / "06_scene_test_apercu.png"
CRS_UTM = "EPSG:32631"
BANDES = ["lwir11", "qa", "cdist", "qa_pixel", "red", "nir08"]
NODATA_DEFAUT = {"qa_pixel": 1}   # USGS : valeur 1 = bit 0 « Fill » seul (absente des fichiers)

# Valeurs de la passation (USGS) pour comparer aux métadonnées
ECHELLE_ST, DECALAGE_ST = 0.00341802, 149.0
ECHELLE_SR, DECALAGE_SR = 0.0000275, -0.2

# QA_PIXEL Landsat 8-9 (USGS) : bit 0 Fill, 1 Dilated Cloud, 2 Cirrus, 3 Cloud, 4 Cloud Shadow, 7 Water
MASQUE_REMPLISSAGE = 1 << 0
MASQUE_NON_CLAIR = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)
BIT_EAU = 1 << 7

# Zones du contrôle de bon sens (WGS84 : lon_min, lat_min, lon_max, lat_max), approximatives
ZONE_FORET = (4.415, 50.772, 4.440, 50.787)    # forêt de Soignes, partie bruxelloise
ZONE_CENTRE = (4.345, 50.840, 4.365, 50.852)   # Pentagone, autour de la Grand-Place

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


# --- 1. Fichiers ---
print("--- Fichiers ---")
fiches = sorted(DOSSIER.glob("*_stac.json"))
ids = [f.name.replace("_stac.json", "") for f in fiches]
note(len(ids) >= 1, f"{len(ids)} scène(s) : {ids}")
manquants = [f"{i}_{b}.tif" for i in ids for b in BANDES if not (DOSSIER / f"{i}_{b}.tif").exists()]
note(not manquants, f"les {len(ids) * len(BANDES)} fichiers de bandes sont présents" + (f" (manquants : {manquants})" if manquants else ""))
if manquants or not ids:
    sys.exit(1)

# --- 2. Facteurs d'échelle lus dans les métadonnées STAC ---
print("\n--- Facteurs d'échelle (métadonnées du catalogue) ---")
fiche = json.loads(fiches[0].read_text(encoding="utf-8"))


def facteurs(bande):
    """Renvoie (échelle, décalage) déclarés dans la fiche STAC, ou (None, None)."""
    infos = fiche["assets"][bande].get("raster:bands", [{}])[0]
    return infos.get("scale"), infos.get("offset")


ech_st, dec_st = facteurs("lwir11")
note(ech_st is not None and np.isclose(ech_st, ECHELLE_ST) and np.isclose(dec_st, DECALAGE_ST),
     f"lwir11 : échelle {ech_st}, décalage {dec_st} (passation : {ECHELLE_ST}, {DECALAGE_ST})")
for bande in ["red", "nir08"]:
    ech, dec = facteurs(bande)
    note(ech is not None and np.isclose(ech, ECHELLE_SR) and np.isclose(dec, DECALAGE_SR),
         f"{bande} : échelle {ech}, décalage {dec} (passation : {ECHELLE_SR}, {DECALAGE_SR})")
ech_qa, _ = facteurs("qa")
ech_cd, _ = facteurs("cdist")
print(f"INFO  qa (ST_QA) : échelle {ech_qa} ; cdist : échelle {ech_cd}")
print(f"INFO  résolution déclarée de lwir11 : {fiche['assets']['lwir11'].get('gsd', 'non indiquée')} m")
# Si les métadonnées manquent, on continue avec les valeurs de la passation (le FAIL ci-dessus le signale)
ech_st, dec_st = (ech_st, dec_st) if ech_st is not None else (ECHELLE_ST, DECALAGE_ST)
ech_qa = ech_qa if ech_qa is not None else 0.01
ech_cd = ech_cd if ech_cd is not None else 0.01


# --- 3. Assemblage des deux scènes du passage (lignes 024 et 025), bande par bande ---
def assembler(bande):
    """Assemble les scènes du passage : la première valeur valide est gardée."""
    couches = []
    for i in ids:
        couche = rioxarray.open_rasterio(DOSSIER / f"{i}_{bande}.tif").squeeze("band", drop=True)
        # QA_PIXEL ne déclare pas sa valeur vide : sans elle, l'assemblage garderait la 1re scène partout
        if couche.rio.nodata is None and bande in NODATA_DEFAUT:
            couche = couche.rio.write_nodata(NODATA_DEFAUT[bande])
        couches.append(couche)
    if len(couches) == 1:
        return couches[0]
    return merge_arrays(couches, nodata=couches[0].rio.nodata)


print("\n--- Grille ---")
donnees = {b: assembler(b) for b in BANDES}
sans_nodata = [b for b, d in donnees.items() if d.rio.nodata is None]
note(not sans_nodata, "valeur vide (nodata) connue pour chaque bande" + (f" (inconnue : {sans_nodata})" if sans_nodata else ""))
ref = donnees["qa_pixel"]
meme_grille = all(d.shape == ref.shape and d.rio.transform() == ref.rio.transform() for d in donnees.values())
note(meme_grille, f"les 6 bandes sont sur la même grille ({ref.shape[1]} x {ref.shape[0]} pixels)")
note(ref.rio.crs.to_string() == CRS_UTM, f"CRS : {ref.rio.crs.to_string()} (attendu : {CRS_UTM})")

region = gpd.read_file(config.DATA_BRUT / "urbis_region.geojson").to_crs(CRS_UTM)
dans = geometry_mask([region.geometry.union_all()], out_shape=ref.shape, transform=ref.rio.transform(), invert=True)
n_region = dans.sum()


def masque_zone(zone_wgs84):
    """Pixels d'une zone rectangulaire WGS84, limités à la Région."""
    geom = gpd.GeoSeries([box(*zone_wgs84)], crs=4326).to_crs(CRS_UTM).iloc[0]
    return dans & geometry_mask([geom], out_shape=ref.shape, transform=ref.rio.transform(), invert=True)


# --- 4. Masques ---
qa_pixel = donnees["qa_pixel"].values
clair = ((qa_pixel & MASQUE_REMPLISSAGE) == 0) & ((qa_pixel & MASQUE_NON_CLAIR) == 0)
# La part claire doit être celle trouvée par l'audit 04 pour ce passage (même calcul, autre script)
pct_clair = 100 * (dans & clair).sum() / n_region
morceaux = ids[0].split("_")                       # ex. LC08_L2SP_198024_20250713_02_T1
passage = f"{morceaux[3][:4]}-{morceaux[3][4:6]}-{morceaux[3][6:]}_{morceaux[2][:3]}"
audit04 = pd.read_csv(config.AUDIT / "04_part_claire_passages.csv", sep=";", decimal=",", dtype={"passage": str})
attendu = audit04.loc[audit04["passage"] == passage, "pct_claire"]
note(len(attendu) == 1 and abs(pct_clair - attendu.iloc[0]) <= 0.5,
     f"part de la Région claire : {pct_clair:.2f} % (audit 04 pour {passage} : "
     f"{attendu.iloc[0] if len(attendu) else 'introuvable'} %, écart max 0,5 point)")
print(f"INFO  pixels d'eau (bit 7) dans la Région : {100 * (dans & ((qa_pixel & BIT_EAU) != 0)).sum() / n_region:.2f} %")

# --- 5. Température de surface ---
print("\n--- Température de surface (LST) ---")
dn_st = donnees["lwir11"].values.astype("float64")
st_valide = dn_st != donnees["lwir11"].rio.nodata
lst = np.where(st_valide, dn_st * ech_st + dec_st - 273.15, np.nan)   # K -> °C
trous = dans & clair & ~st_valide
pct_trous = 100 * trous.sum() / n_region
note(pct_trous <= 1, f"trous d'émissivité (pixels clairs sans LST) : {pct_trous:.2f} % de la Région (max 1 %)")

utile = dans & clair & st_valide
mediane = np.nanmedian(lst[utile])
p1, p99 = np.nanpercentile(lst[utile], [1, 99])
note(20 <= mediane <= 45, f"LST médiane de la Région : {mediane:.1f} °C (attendu entre 20 et 45)")
note(5 <= p1 and p99 <= 65, f"LST 1er centile {p1:.1f} °C, 99e centile {p99:.1f} °C (attendu entre 5 et 65)")
print(f"INFO  LST min {np.nanmin(lst[utile]):.1f} °C, max {np.nanmax(lst[utile]):.1f} °C")

qa_st = donnees["qa"].values.astype("float64")
qa_valide = utile & (qa_st != donnees["qa"].rio.nodata)
incert = qa_st[qa_valide] * ech_qa
print(f"INFO  incertitude ST_QA : médiane {np.median(incert):.2f} K, 95e centile {np.percentile(incert, 95):.2f} K")
cdist = donnees["cdist"].values.astype("float64")
cd_valide = utile & (cdist != donnees["cdist"].rio.nodata)
print(f"INFO  distance aux nuages : médiane {np.median(cdist[cd_valide] * ech_cd):.1f} km, "
      f"part < 1 km : {100 * (cdist[cd_valide] * ech_cd < 1).mean():.2f} %")

# --- 6. NDVI ---
print("\n--- NDVI ---")
ech_sr, dec_sr = facteurs("red")
ech_sr, dec_sr = (ech_sr, dec_sr) if ech_sr is not None else (ECHELLE_SR, DECALAGE_SR)
rouge_dn, pir_dn = donnees["red"].values.astype("float64"), donnees["nir08"].values.astype("float64")
sr_valide = (rouge_dn != donnees["red"].rio.nodata) & (pir_dn != donnees["nir08"].rio.nodata)
rouge, pir = rouge_dn * ech_sr + dec_sr, pir_dn * ech_sr + dec_sr
somme = pir + rouge
ok_ndvi = dans & clair & sr_valide & (somme != 0)
ndvi = np.where(ok_ndvi, (pir - rouge) / np.where(somme == 0, 1, somme), np.nan)
dans_bornes = 100 * (np.abs(ndvi[ok_ndvi]) <= 1).mean()
note(dans_bornes >= 99.9, f"NDVI dans [-1, 1] pour {dans_bornes:.2f} % des pixels (min 99,9 %)")
ndvi_med = np.nanmedian(ndvi[ok_ndvi])
note(0.3 <= ndvi_med <= 0.6, f"NDVI médian de la Région : {ndvi_med:.2f} (attendu entre 0,3 et 0,6)")

# --- 7. Contrôle de bon sens : forêt contre centre-ville ---
print("\n--- Bon sens : forêt de Soignes contre Pentagone ---")
foret, centre = masque_zone(ZONE_FORET), masque_zone(ZONE_CENTRE)
zones_ok = True
for nom, zone in [("forêt", foret), ("centre", centre)]:
    z = zone & utile
    note(z.sum() >= 50, f"zone {nom} : {z.sum()} pixels clairs avec LST (min 50)")
    zones_ok = zones_ok and z.sum() >= 50
    if z.sum() >= 50:
        print(f"INFO  {nom} : LST médiane {np.nanmedian(lst[z]):.1f} °C, NDVI médian {np.nanmedian(ndvi[zone & ok_ndvi]):.2f}")
if zones_ok:
    ecart = np.nanmedian(lst[centre & utile]) - np.nanmedian(lst[foret & utile])
    note(ecart > 0, f"le centre est plus chaud que la forêt (écart {ecart:.1f} °C)")
    if np.nanmedian(ndvi[foret & ok_ndvi]) < 0.6:
        print("INFO  NDVI de la zone « forêt » < 0,6 : la zone contient peut-être autre chose que de la forêt")

# --- 8. Aperçu visuel ---
config.AUDIT.mkdir(parents=True, exist_ok=True)
xmin, ymax = ref.rio.transform().c, ref.rio.transform().f
etendue = [xmin, xmin + ref.shape[1] * 30, ymax - ref.shape[0] * 30, ymax]
fig, axes = plt.subplots(1, 2, figsize=(13, 6))
for ax, valeurs, titre, cmap in [(axes[0], np.where(utile, lst, np.nan), "LST (°C)", "inferno"),
                                  (axes[1], np.where(ok_ndvi, ndvi, np.nan), "NDVI", "RdYlGn")]:
    vmin, vmax = np.nanpercentile(valeurs, [2, 98])   # bornes aux 2e et 98e centiles
    image = ax.imshow(valeurs, extent=etendue, cmap=cmap, vmin=vmin, vmax=vmax)
    region.boundary.plot(ax=ax, color="black", linewidth=0.6)
    gpd.GeoSeries([box(*ZONE_FORET), box(*ZONE_CENTRE)], crs=4326).to_crs(CRS_UTM).boundary.plot(ax=ax, color="cyan", linewidth=1)
    fig.colorbar(image, ax=ax, shrink=0.8)
    ax.set_title(titre)
    ax.set_axis_off()
fig.suptitle(f"Passage test {', '.join(ids)} — bande thermique déclarée à 100 m, livrée à 30 m")
fig.savefig(FICHIER_APERCU, dpi=110, bbox_inches="tight")
print(f"\nAperçu écrit : {FICHIER_APERCU.relative_to(RACINE)}")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

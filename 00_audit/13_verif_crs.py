# 13_verif_crs.py — contrôle en LECTURE SEULE des CRS de toutes les données brutes (phase 2, étape 2.1)
# Pour chaque fichier de data/brut/<ville>/ : CRS déclaré, emprise, cohérence avec la Région,
# et transformation que PROJ utilisera pour passer au CRS de calcul (config.CRS_CALCUL).
# Ne crée, ne modifie et ne télécharge rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\13_verif_crs.py

import sys
import warnings
from pathlib import Path

import pyogrio
import rasterio
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup
from shapely.geometry import box

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

# PROJ avertit quand une grille de correction manque : on le signale nous-mêmes en INFO (bloc 5)
warnings.filterwarnings("ignore", message="Best transformation is not available")

CRS_RASTER_ATTENDU = "EPSG:32631"   # UTM 31N : les rasters Landsat restent dans ce CRS
EXT_VECTEUR = {".gpkg", ".geojson", ".json", ".gml", ".xml", ".shp", ".fgb", ".kml"}
EXT_RASTER = {".tif", ".tiff"}
EXT_TABLE = {".xlsx", ".xls", ".csv", ".txt"}

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    print(f"INFO  {message}")


def emprise_wgs84(crs, bornes):
    """Ramène une emprise (xmin, ymin, xmax, ymax) en WGS84, ordre lon/lat."""
    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return t.transform_bounds(*bornes)


def emprise_calcul(crs, bornes):
    """Ramène une emprise dans le CRS de calcul."""
    t = Transformer.from_crs(crs, config.CRS_CALCUL, always_xy=True)
    return t.transform_bounds(*bornes)


ZONE = box(*config.EMPRISE_WGS84)   # rectangle qui contient la Région (audit 03)
crs_sources = {}                    # CRS rencontrés -> liste des fichiers


def controle_emprise(nom, crs, bornes):
    """PASS si l'emprise, ramenée en WGS84, touche le rectangle de la Région.
    Des axes inversés (lat/lon) envoient la couche ailleurs, donc FAIL."""
    lon_min, lat_min, lon_max, lat_max = emprise_wgs84(crs, bornes)
    touche = box(lon_min, lat_min, lon_max, lat_max).intersects(ZONE)
    x0, y0, x1, y1 = emprise_calcul(crs, bornes)
    note(touche, f"{nom} : emprise WGS84 ({lon_min:.3f}, {lat_min:.3f}, {lon_max:.3f}, {lat_max:.3f}) "
                 f"{'touche' if touche else 'NE TOUCHE PAS'} la Région ; en {config.CRS_CALCUL} : "
                 f"({x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f})")


# --- 1. Paramètres ---
print("--- config.py ---")
note(config.CRS_CALCUL == "EPSG:31370", f"CRS_CALCUL = {config.CRS_CALCUL!r} (attendu : 'EPSG:31370')")
if config.CRS_CALCUL is None:
    sys.exit("Arrêt : mets d'abord CRS_CALCUL = \"EPSG:31370\" dans config.py")
note(config.DATA_BRUT.is_dir(), f"dossier {config.DATA_BRUT.relative_to(RACINE)}")

fichiers = sorted(p for p in config.DATA_BRUT.rglob("*") if p.is_file())
info(f"{len(fichiers)} fichier(s) trouvé(s)")

# --- 2. Couches vectorielles ---
print("\n--- Couches vectorielles ---")
non_lus = []
for chemin in fichiers:
    if chemin.suffix.lower() not in EXT_VECTEUR:
        continue
    nom_court = chemin.relative_to(config.DATA_BRUT)
    try:
        couches = [c[0] for c in pyogrio.list_layers(chemin)]
    except Exception:
        non_lus.append(nom_court)   # ex. fiche STAC .json : pas une couche géographique
        continue
    for couche in couches:
        nom = f"{nom_court}" + (f" [{couche}]" if len(couches) > 1 else "")
        try:
            meta = pyogrio.read_info(chemin, layer=couche, force_total_bounds=True, force_feature_count=True)
        except Exception as erreur:
            non_lus.append(f"{nom} ({erreur})")
            continue
        bornes = meta.get("total_bounds")
        if meta.get("geometry_type") is None or bornes is None or any(b != b for b in bornes):
            info(f"{nom} : pas de géométrie exploitable, {meta['features']} ligne(s)")
            continue
        if not meta["crs"]:
            note(False, f"{nom} : AUCUN CRS déclaré")
            continue
        crs = CRS.from_user_input(meta["crs"])
        crs_sources.setdefault(crs.to_string(), []).append(nom)
        note(True, f"{nom} : {crs.to_string()} ({crs.name}), {meta['features']} objets, {meta['geometry_type']}")
        controle_emprise(nom, crs, bornes)

# --- 3. Rasters (résumés par dossier : il y a un fichier par bande) ---
print("\n--- Rasters ---")
par_dossier = {}
for chemin in fichiers:
    if chemin.suffix.lower() in EXT_RASTER:
        par_dossier.setdefault(chemin.parent, []).append(chemin)
for dossier, tifs in par_dossier.items():
    nom = dossier.relative_to(config.DATA_BRUT)
    crs_vus, bornes = set(), None
    for tif in tifs:
        with rasterio.open(tif) as r:       # ouverture en lecture seule
            crs_vus.add(r.crs.to_string() if r.crs else None)
            if r.crs and bornes is None:
                bornes = (r.crs, tuple(r.bounds))
    note(None not in crs_vus, f"{nom} : {len(tifs)} raster(s), CRS : {sorted(map(str, crs_vus))}")
    note(crs_vus == {CRS_RASTER_ATTENDU},
         f"{nom} : tous en {CRS_RASTER_ATTENDU} (pas de reprojection des pixels prévue)")
    if bornes:
        controle_emprise(f"{nom} (1er fichier)", *bornes)

# --- 4. Fichiers non géographiques ---
print("\n--- Autres fichiers ---")
for chemin in fichiers:
    if chemin.suffix.lower() in EXT_TABLE:
        info(f"{chemin.relative_to(config.DATA_BRUT)} : table, pas de CRS (jointure par code)")
for nom in non_lus:
    info(f"{nom} : pas lu comme couche géographique (à confirmer que c'est normal)")
autres = [c for c in fichiers if c.suffix.lower() not in EXT_VECTEUR | EXT_RASTER | EXT_TABLE]
for chemin in autres:
    info(f"{chemin.relative_to(config.DATA_BRUT)} : extension non contrôlée")

# --- 5. Transformations vers le CRS de calcul (une par CRS source) ---
print(f"\n--- Transformations vers {config.CRS_CALCUL} ---")
for crs_txt, noms in crs_sources.items():
    if CRS.from_user_input(crs_txt) == CRS.from_user_input(config.CRS_CALCUL):
        info(f"{crs_txt} : déjà dans le CRS de calcul ({len(noms)} couche(s))")
        continue
    groupe = TransformerGroup(crs_txt, config.CRS_CALCUL, always_xy=True)
    if not groupe.transformers:
        note(False, f"{crs_txt} -> {config.CRS_CALCUL} : aucune transformation disponible")
        continue
    t = groupe.transformers[0]   # celle que PROJ utilise par défaut
    precision = f"{t.accuracy} m" if t.accuracy is not None and t.accuracy >= 0 else "inconnue"
    note(True, f"{crs_txt} -> {config.CRS_CALCUL} ({len(noms)} couche(s)) : {t.description} ; précision {precision}")
    if not groupe.best_available:
        info(f"  une transformation plus précise existe mais sa grille n'est pas installée "
             f"({len(groupe.unavailable_operations)} opération(s) indisponible(s))")

print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")

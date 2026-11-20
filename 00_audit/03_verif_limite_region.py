# 03_verif_limite_region.py
# Contrôle en LECTURE SEULE du contour régional téléchargé par 01_acquisition/02_telecharger_limite_region.py
# Critères fixés avant de voir les données (journal, 18/11/2026).
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\03_verif_limite_region.py

import sys
from pathlib import Path

import geopandas as gpd
from shapely.validation import explain_validity

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

FICHIER = config.DATA_BRUT / "urbis_region.geojson"

# Emprise des quartiers du Monitoring, déclarée dans le GetCapabilities du WFS UrbIS (lu le 18/11/2026)
EMPRISE_REFERENCE = (4.2435, 50.7636, 4.4826, 50.9139)   # lon_min, lat_min, lon_max, lat_max
TOLERANCE_DEG = 0.01                                       # ~1 km
SURFACE_MIN_KM2, SURFACE_MAX_KM2 = 155, 170                # passation : ~162 km² (à vérifier IBSA)
# Plage plausible de Bruxelles en Lambert 72 (x = est, y = nord), en mètres
X_MIN, X_MAX = 130_000, 170_000
Y_MIN, Y_MAX = 155_000, 185_000

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


# --- 1. Lecture ---
print("--- Fichier ---")
if not FICHIER.exists():
    note(False, f"{FICHIER.relative_to(RACINE)} absent : lancer d'abord le script 02")
    sys.exit(1)
region = gpd.read_file(FICHIER)
note(len(region) >= 1, f"{len(region)} entité(s) lue(s)")
print(f"INFO  colonnes : {[c for c in region.columns if c != 'geometry']}")
print(f"INFO  type(s) de géométrie : {region.geom_type.unique().tolist()}")

# --- 2. CRS et ordre des axes ---
print("\n--- CRS et axes ---")
epsg = region.crs.to_epsg() if region.crs is not None else None
note(epsg == 31370, f"CRS lu : EPSG:{epsg} (attendu : 31370, Lambert 72)")
xmin, ymin, xmax, ymax = region.total_bounds
print(f"INFO  emprise (m) : x {xmin:,.0f} à {xmax:,.0f} ; y {ymin:,.0f} à {ymax:,.0f}")
note(X_MIN <= xmin and xmax <= X_MAX and Y_MIN <= ymin and ymax <= Y_MAX,
     "coordonnées dans la plage plausible de Bruxelles en Lambert 72 (axes dans le bon ordre)")

# --- 3. Géométrie ---
print("\n--- Géométrie ---")
valide = region.is_valid.all()
note(valide, "géométrie valide")
if not valide:
    for raison in region.geometry[~region.is_valid].apply(explain_validity):
        print(f"      raison : {raison}")
surface_km2 = region.area.sum() / 1e6
note(SURFACE_MIN_KM2 <= surface_km2 <= SURFACE_MAX_KM2,
     f"surface : {surface_km2:.2f} km² (attendu entre {SURFACE_MIN_KM2} et {SURFACE_MAX_KM2})")
n_parties = region.geometry.explode(index_parts=True).shape[0]
print(f"INFO  nombre de polygones (parties) : {n_parties}")

# --- 4. Emprise en WGS84 ---
print("\n--- Emprise WGS84 ---")
lon_min, lat_min, lon_max, lat_max = region.to_crs(4326).total_bounds
print(f"INFO  emprise WGS84 : ({lon_min:.4f}, {lat_min:.4f}, {lon_max:.4f}, {lat_max:.4f})")
ecart = max(abs(a - b) for a, b in zip((lon_min, lat_min, lon_max, lat_max), EMPRISE_REFERENCE))
note(ecart <= TOLERANCE_DEG,
     f"proche de l'emprise des quartiers du Monitoring (écart max {ecart:.4f}°, tolérance {TOLERANCE_DEG}°)")

c_lon_min, c_lat_min, c_lon_max, c_lat_max = config.EMPRISE_WGS84
contenue = (c_lon_min <= lon_min and lat_max <= c_lat_max and c_lat_min <= lat_min and lon_max <= c_lon_max)
note(contenue, f"la Région est entièrement dans EMPRISE_WGS84 de config.py {config.EMPRISE_WGS84}")
marge = min(lon_min - c_lon_min, c_lon_max - lon_max, lat_min - c_lat_min, c_lat_max - lat_max)
print(f"INFO  plus petite marge entre la Région et l'emprise de config.py : {marge:.3f}°")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

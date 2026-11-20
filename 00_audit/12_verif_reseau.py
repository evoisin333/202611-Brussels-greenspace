# 12_verif_reseau.py
# Contrôle en LECTURE SEULE du réseau téléchargé par 01_acquisition/11_telecharger_reseau.py.
# Critères fixés avant les données (journal, 20/11/2026) :
#   - emprise OSM couvrant toute la Région ; CRS et axes des axes UrbIS
#   - couverture : ≥ 98 % de la longueur des axes UrbIS (dans la Région) à moins de 15 m d'une voie OSM
#   - connexité : ≥ 95 % de la longueur du réseau piéton OSM dans le plus grand bloc connecté
#   - chemins dans les grands parcs (Bois de la Cambre, parc de Laeken, forêt de Soignes) : longueur > 0
# Filtre « piéton » PROVISOIRE (pour l'audit seulement ; le filtre définitif se fixe en phase 2).
# Aucun fichier écrit.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\12_verif_reseau.py

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

DOSSIER = config.DATA_BRUT / "reseau"
FICHIER_OSM = DOSSIER / "osm_highway_20261101.json"
FICHIER_URBIS = DOSSIER / "urbis_axes_rues.geojson"
FICHIER_EV = config.DATA_BRUT / "bruxelles_environnement" / "espaces_verts_accessibles.geojson"
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"

DISTANCE_COUVERTURE_M = 15
PAS_ECHANTILLON_M = 10
MIN_COUVERTURE = 0.98
MIN_CONNEXITE = 0.95
X_MIN, X_MAX = 130_000, 170_000   # plage plausible de Bruxelles en Lambert 72 (m)
Y_MIN, Y_MAX = 155_000, 185_000
# Filtre piéton provisoire : on écarte les voies interdites ou non construites
NON_PIETON = {"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway", "abandoned", "platform"}
CHEMINS = {"footway", "path", "pedestrian", "steps", "track", "cycleway", "bridleway"}
PARCS = {"Bois de la Cambre": "Cambre", "parc de Laeken": "Laeken", "forêt de Soignes": "Soignes"}

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


region = gpd.read_file(FICHIER_REGION).to_crs(31370)
geom_region = region.geometry.union_all()

# --- 1. OSM : des voies Overpass aux lignes ---
print("--- OpenStreetMap ---")
voies = [e for e in json.loads(FICHIER_OSM.read_text(encoding="utf-8"))["elements"] if e.get("type") == "way"]
lignes = []
for v in voies:
    coords = [(p["lon"], p["lat"]) for p in v.get("geometry", []) if p]   # p vide = nœud hors emprise
    if len(coords) >= 2 and len(coords) == len(v.get("nodes", [])):
        tags = v.get("tags", {})
        lignes.append({"osm_id": v["id"], "highway": tags.get("highway"), "access": tags.get("access"),
                       "foot": tags.get("foot"), "bridge": tags.get("bridge"),
                       "noeuds": v["nodes"], "geometry": LineString(coords)})
osm = gpd.GeoDataFrame(lignes, crs=4326).to_crs(31370)
print(f"INFO  {len(voies)} voies, {len(osm)} converties en lignes complètes (les autres coupent le bord de l'emprise)")
osm["longueur"] = osm.length
note(osm.total_bounds[0] <= region.total_bounds[0] and osm.total_bounds[1] <= region.total_bounds[1]
     and osm.total_bounds[2] >= region.total_bounds[2] and osm.total_bounds[3] >= region.total_bounds[3],
     "l'emprise du réseau OSM couvre toute la Région")
print(f"INFO  longueur totale : {osm['longueur'].sum() / 1000:,.0f} km ; par type (km, 12 premiers) :")
for type_voie, km in (osm.groupby("highway")["longueur"].sum() / 1000).sort_values(ascending=False).head(12).items():
    print(f"        {type_voie:<16} {km:8.1f}")

pieton = osm[~osm["highway"].isin(NON_PIETON)
             & ~osm["access"].isin(["private", "no"]) & ~osm["foot"].isin(["no", "private"])].copy()
print(f"INFO  réseau piéton provisoire : {len(pieton)} voies, {pieton['longueur'].sum() / 1000:,.0f} km "
      f"({100 * (1 - len(pieton) / len(osm)):.1f} % des voies écartées : autoroutes, privées, interdites aux piétons…)")
print(f"INFO  voies OSM marquées « pont » (bridge) dans le réseau piéton : {pieton['bridge'].notna().sum()}")

# --- 2. Axes de rues UrbIS ---
print("\n--- Axes de rues UrbIS ---")
urbis = gpd.read_file(FICHIER_URBIS)
epsg = urbis.crs.to_epsg() if urbis.crs is not None else None
note(epsg == 31370, f"CRS : EPSG:{epsg} (attendu 31370)")
xmin, ymin, xmax, ymax = urbis.total_bounds
note(X_MIN <= xmin and xmax <= X_MAX and Y_MIN <= ymin and ymax <= Y_MAX,
     f"coordonnées dans la plage de Bruxelles (x {xmin:,.0f}-{xmax:,.0f}, y {ymin:,.0f}-{ymax:,.0f})")
urbis_region = gpd.clip(urbis.set_crs(31370, allow_override=True), geom_region)
print(f"INFO  {len(urbis)} axes, {urbis_region.length.sum() / 1000:,.0f} km dans la Région")

# --- 3. Couverture : chaque mètre de rue officielle a-t-il une voie OSM à moins de 15 m ? ---
points = []
for geom in urbis_region.geometry.explode(index_parts=False):
    if geom is None or geom.is_empty:
        continue
    for d in np.arange(0, geom.length, PAS_ECHANTILLON_M):
        points.append(geom.interpolate(d))
echantillon = gpd.GeoDataFrame(geometry=points, crs=31370)
proches = gpd.sjoin_nearest(echantillon, osm[["geometry"]], max_distance=DISTANCE_COUVERTURE_M, how="left")
couverts = proches.groupby(level=0)["index_right"].first().notna()
couverture = couverts.mean()
note(couverture >= MIN_COUVERTURE, f"couverture des rues UrbIS par OSM : {100 * couverture:.2f} % "
     f"(points tous les {PAS_ECHANTILLON_M} m à moins de {DISTANCE_COUVERTURE_M} m ; min 98 %)")

# --- 4. Connexité du réseau piéton provisoire ---
print("\n--- Connexité ---")
# Deux voies sont reliées si elles partagent un nœud OSM : on relie les nœuds consécutifs de chaque voie
identifiants = {}
debuts, fins = [], []
for noeuds in pieton["noeuds"]:
    indices = [identifiants.setdefault(n, len(identifiants)) for n in noeuds]
    debuts.extend(indices[:-1])
    fins.extend(indices[1:])
n = len(identifiants)
graphe = coo_matrix((np.ones(len(debuts)), (debuts, fins)), shape=(n, n))
n_blocs, etiquettes = connected_components(graphe, directed=False)
pieton["bloc"] = [etiquettes[identifiants[noeuds[0]]] for noeuds in pieton["noeuds"]]
longueur_par_bloc = pieton.groupby("bloc")["longueur"].sum().sort_values(ascending=False)
part_principal = longueur_par_bloc.iloc[0] / longueur_par_bloc.sum()
print(f"INFO  {n_blocs} blocs connectés ; le 2e plus grand fait {longueur_par_bloc.iloc[1] / 1000:.1f} km" if n_blocs > 1
      else "INFO  un seul bloc connecté")
note(part_principal >= MIN_CONNEXITE, f"part de la longueur dans le plus grand bloc connecté : {100 * part_principal:.2f} % (min 95 %)")

# --- 5. Chemins dans les grands parcs ---
print("\n--- Chemins dans les grands parcs ---")
ev = gpd.read_file(FICHIER_EV).set_crs(31370, allow_override=True)
chemins = pieton[pieton["highway"].isin(CHEMINS)]
for nom, motcle in PARCS.items():
    parc = ev[ev["name_f"].astype(str).str.contains(motcle, case=False)]
    if parc.empty:
        note(False, f"{nom} : introuvable dans la couche des espaces verts (mot-clé « {motcle} »)")
        continue
    km = gpd.clip(chemins, parc.geometry.union_all()).length.sum() / 1000
    note(km > 0, f"{nom} : {km:.1f} km de chemins OSM à l'intérieur ({parc.area.sum() / 1e4:.0f} ha)")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

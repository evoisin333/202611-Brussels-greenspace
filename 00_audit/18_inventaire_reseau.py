# 18_inventaire_reseau.py — inventaire en LECTURE SEULE du réseau OSM (phase 2, étape 2.3)
# But : voir ce que chaque règle du filtre piéton retire, la connexité qui en résulte,
# et comment les espaces verts du filtre principal touchent le réseau (entrées), AVANT de figer la règle.
# Ne crée, ne modifie et n'écrit rien. Aucun croisement avec la chaleur ou la population.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\18_inventaire_reseau.py > data\travail\bruxelles\audit\18_sortie.txt

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et outils_ev.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_ev import charger_ev, masque_filtre_principal

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

FICHIER_OSM = config.DATA_BRUT / "reseau" / "osm_highway_20261101.json"
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"

# --- Règle piétonne proposée (étape 2.3) ---
NON_CONSTRUIT = {"construction", "proposed", "planned", "abandoned", "razed", "disused"}
TYPE_EXCLU = {"raceway", "bus_guideway", "platform", "rest_area", "services", "escape", "no"}
AUTOROUTE = {"motorway", "motorway_link", "trunk", "trunk_link"}   # foot=no par défaut en Belgique
CHEMIN_PIETON = {"footway", "path", "pedestrian", "steps"}
FOOT_OUI = {"yes", "designated", "permissive", "official", "destination"}
INTERDIT = {"no", "private"}
INTERIEUR = {"corridor", "elevator"}
SEUILS_DIFFUS_M = [5, 10, 15, 20, 30]

pd.set_option("display.width", 200)


def info(message):
    print(f"INFO  {message}")


def raison_exclusion(t):
    """Première règle qui exclut la voie (None = gardée). Ordre = ordre de la cascade."""
    hw, foot = t.get("highway"), t.get("foot")
    if hw in NON_CONSTRUIT:
        return "1 non construite / hors usage"
    if hw in TYPE_EXCLU:
        return "2 type exclu (raceway, platform…)"
    if t.get("area") == "yes":
        return "3 aire (area=yes)"
    if t.get("service") == "private":
        return "4 service=private"
    if foot in INTERDIT:
        return "5 foot interdit"
    if foot not in FOOT_OUI and t.get("access") in INTERDIT:
        return "6 access interdit"
    if foot not in FOOT_OUI and hw in AUTOROUTE:
        return "7 autoroute / trunk"
    if t.get("tunnel") in ("yes", "culvert") and hw not in CHEMIN_PIETON and foot not in FOOT_OUI:
        return "8 tunnel routier"
    return None


def km(serie):
    return round(serie.sum() / 1000, 1)


# --- 1. Lecture des voies OSM ---
print("--- 1. Voies OSM ---")
region = gpd.read_file(FICHIER_REGION).to_crs(config.CRS_CALCUL)
geom_region = region.geometry.union_all()
voies = [e for e in json.loads(FICHIER_OSM.read_text(encoding="utf-8"))["elements"] if e.get("type") == "way"]
lignes = []
for v in voies:
    coords = [(p["lon"], p["lat"]) for p in v.get("geometry", []) if p]   # p vide = nœud hors emprise
    if len(coords) >= 2 and len(coords) == len(v.get("nodes", [])):
        t = v.get("tags", {})
        lignes.append({"osm_id": v["id"], "highway": t.get("highway"), "name": t.get("name"),
                       "access": t.get("access"), "foot": t.get("foot"), "service": t.get("service"),
                       "tunnel": t.get("tunnel"), "area": t.get("area"), "indoor": t.get("indoor"),
                       "sidewalk": t.get("sidewalk"), "raison": raison_exclusion(t),
                       "noeuds": v["nodes"], "geometry": LineString(coords)})
osm = gpd.GeoDataFrame(lignes, crs=4326).to_crs(config.CRS_CALCUL)
osm["longueur"] = osm.length
osm["dans_region"] = osm.intersects(geom_region)
info(f"{len(voies)} voies lues, {len(osm)} complètes ; {km(osm['longueur'])} km (dont {km(osm.loc[osm['dans_region'], 'longueur'])} km touchant la Région)")

print("\n[km par type de voie]")
print((osm.groupby("highway")["longueur"].sum() / 1000).round(1).sort_values(ascending=False).to_string())

for col in ["access", "foot", "service", "tunnel", "area", "indoor", "sidewalk"]:
    print(f"\n[{col} : km par valeur (10 premières)]")
    print((osm.groupby(col, dropna=False)["longueur"].sum() / 1000).round(1).sort_values(ascending=False).head(10).to_string())

# --- 2. Cascade du filtre piéton ---
print("\n--- 2. Cascade du filtre piéton (première règle qui exclut) ---")
cascade = osm.groupby(osm["raison"].fillna("0 gardée"))["longueur"].agg(voies="size", km="sum")
cascade["km"] = (cascade["km"] / 1000).round(1)
print(cascade.to_string())

tunnels = osm[osm["raison"] == "8 tunnel routier"].sort_values("longueur", ascending=False)
print("\n[10 plus longs tunnels exclus : à vérifier à l'œil]")
print(tunnels[["osm_id", "highway", "name", "foot", "longueur"]].head(10).round(0).to_string(index=False))

garde = osm[osm["raison"].isna()].copy()
interieur = garde[garde["highway"].isin(INTERIEUR) | (garde["indoor"] == "yes")]
print(f"\n[voies intérieures gardées (corridor, elevator, indoor=yes) : {len(interieur)} voies, {km(interieur['longueur'])} km]")
print((interieur.groupby("highway")["longueur"].sum() / 1000).round(2).to_string())
sep = garde[garde["sidewalk"] == "separate"]
info(f"rues à trottoir séparé (sidewalk=separate) gardées : {len(sep)} voies, {km(sep['longueur'])} km")

# --- 3. Connexité du réseau gardé ---
print("\n--- 3. Connexité ---")
ids = {n: i for i, n in enumerate({n for ns in garde["noeuds"] for n in ns})}
a = [ids[n] for ns in garde["noeuds"] for n in ns[:-1]]
b = [ids[n] for ns in garde["noeuds"] for n in ns[1:]]
graphe = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(ids), len(ids)))
n_blocs, etiquette = connected_components(graphe, directed=False)
garde["bloc"] = [etiquette[ids[ns[0]]] for ns in garde["noeuds"]]
longueur_bloc = garde.groupby("bloc")["longueur"].sum()
principal = longueur_bloc.idxmax()
isoles = garde[garde["bloc"] != principal]
info(f"{n_blocs} blocs connectés ; le plus grand : {longueur_bloc.max() / longueur_bloc.sum():.2%} de la longueur")
info(f"écartés (hors du plus grand bloc) : {isoles['bloc'].nunique()} blocs, {len(isoles)} voies, {km(isoles['longueur'])} km")
print("[km écartés par type de voie]")
print((isoles.groupby("highway")["longueur"].sum() / 1000).round(2).sort_values(ascending=False).head(10).to_string())

ev = charger_ev(config)
ev = ev[masque_filtre_principal(ev, config)].copy()
union_ev = ev.geometry.union_all()
dans_ev = isoles.intersection(union_ev).length
info(f"dont dans les espaces verts du filtre principal : {dans_ev.sum() / 1000:.2f} km")

# --- 4. Entrées des espaces verts (réseau = plus grand bloc) ---
print("\n--- 4. Entrées des espaces verts ---")
reseau = garde[garde["bloc"] == principal][["osm_id", "geometry"]].reset_index(drop=True)
ev = ev.reset_index(drop=True)
ev["id_ev"] = ev.index
paires = gpd.sjoin(reseau, ev[["id_ev", "geometry"]], predicate="intersects")
n_entrees = {}
for _, p in paires.iterrows():
    poly = ev.geometry.iloc[p["id_ev"]]
    ligne = p.geometry
    if ligne.intersection(poly).length > 1:          # la voie pénètre dans l'espace (> 1 m à l'intérieur)
        points = ligne.intersection(poly.boundary)
        n = len(getattr(points, "geoms", [points])) if not points.is_empty else 0
        n_entrees[p["id_ev"]] = n_entrees.get(p["id_ev"], 0) + max(n, 1)
ev["entrees_ponctuelles"] = ev["id_ev"].map(n_entrees).fillna(0).astype(int)
avec = ev[ev["entrees_ponctuelles"] > 0]
sans = ev[ev["entrees_ponctuelles"] == 0].copy()
info(f"{len(avec)} espaces avec entrée(s) ponctuelle(s) ({avec['ha'].sum():.0f} ha) ; "
     f"médiane {avec['entrees_ponctuelles'].median():.0f} entrée(s) par espace")
info(f"{len(sans)} espaces sans aucune voie qui y pénètre ({sans['ha'].sum():.1f} ha) ; "
     f"par sous-type : {sans['subtype_f'].value_counts().to_dict()}")

# Distance entre la limite de ces espaces et la voie la plus proche (pour fixer le seuil des entrées diffuses)
if len(sans):
    proches = gpd.sjoin_nearest(sans[["id_ev", "ha", "geometry"]], reseau, distance_col="distance_m")
    distance = proches.groupby("id_ev")["distance_m"].min()
    print("[distance limite → voie la plus proche, espaces sans entrée ponctuelle (m)]")
    print(distance.describe(percentiles=[0.25, 0.5, 0.75, 0.9]).round(1).to_string())
    for s in SEUILS_DIFFUS_M:
        info(f"à moins de {s} m d'une voie : {(distance <= s).sum()} espaces sur {len(sans)}")
    loin = sans.set_index("id_ev").join(distance).sort_values("distance_m", ascending=False)
    print("[les 10 plus éloignés du réseau]")
    print(loin[["name_f", "subtype_f", "ha", "distance_m"]].head(10).round(1).to_string())

print("\nFin de l'inventaire (lecture seule, aucun fichier écrit).")

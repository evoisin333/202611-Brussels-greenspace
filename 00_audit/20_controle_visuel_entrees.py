# 20_controle_visuel_entrees.py — contrôle visuel des entrées des espaces verts (phase 2, étape 2.3)
# Compare la règle précédente (chaque voie OSM testée seule, limite avec les trous) et la règle corrigée
# (contour extérieur seul, chemins reliés : outils_reseau.points_entrees), sur tout le filtre principal,
# puis exporte 3 espaces témoins
# et les espaces de 1 ha ou plus qui perdent toute entrée ponctuelle, pour les regarder sur un fond de carte.
# Lecture seule sur data/brut ; écrit UN fichier de contrôle : data/travail/<ville>/audit/20_entrees_temoins_v2.gpkg
# Aucun croisement avec la chaleur ou la population.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\20_controle_visuel_entrees.py > data\travail\bruxelles\audit\20_sortie.txt

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et les modules partagés
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_ev import charger_ev, masque_filtre_principal
from outils_reseau import lire_voies_osm, ajouter_blocs, points_entrees

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

FICHIER_OSM = config.DATA_BRUT / "reseau" / "osm_highway_20261101.json"
SORTIE = config.AUDIT / "20_entrees_temoins_v2.gpkg"   # nouveau nom : pas de conflit avec le fichier ouvert dans ArcGIS
# Témoins : un parc clôturé à grilles, un square ouvert, un grand parc (recherche dans name_f, sans casse)
TEMOINS = ["Parc de Bruxelles", "Square Marie-Louise", "Parc Josaphat"]
MARGE_RESEAU_M = 100            # voies exportées autour des témoins


def info(message):
    print(f"INFO  {message}")


def points_entrees_avant(ev, reseau, penetration_m):
    """Règle PRÉCÉDENTE (23/11), gardée ici seulement pour la comparaison : chaque voie OSM est testée
    seule et toute la limite compte, trous compris. Défauts vus sur le parc de Bruxelles le 24/11."""
    paires = gpd.sjoin(reseau[["geometry"]], ev[["id_ev", "geometry"]], predicate="intersects")
    points = []
    for ligne, id_ev in zip(paires.geometry, paires["id_ev"]):
        poly = ev.geometry.iloc[id_ev]
        if ligne.intersection(poly.buffer(-penetration_m)).length > 1:
            croisement = ligne.intersection(poly.boundary)
            for g in getattr(croisement, "geoms", [croisement]):
                if not g.is_empty:
                    points.append({"id_ev": id_ev, "geometry": g.representative_point()})
    return gpd.GeoDataFrame(points, columns=["id_ev", "geometry"], geometry="geometry", crs=ev.crs)


# --- 1. Réseau final et espaces verts du filtre principal ---
osm, _ = lire_voies_osm(FICHIER_OSM, config.CRS_CALCUL)
garde = osm[osm["raison"].isna()].copy()
principal = ajouter_blocs(garde)
reseau = garde[garde["bloc"] == principal].reset_index(drop=True)

ev = charger_ev(config)
ev = ev[masque_filtre_principal(ev, config)].reset_index(drop=True)
ev["id_ev"] = ev.index

# --- 2. Ancienne règle contre nouvelle, sur tous les espaces ---
print("--- Comparaison des règles d'entrée ponctuelle (tout le filtre principal) ---")
p = config.ENTREE_PENETRATION_M
anciens = points_entrees_avant(ev, reseau, p)
nouveaux = points_entrees(ev, reseau, p)
n_anc = ev["id_ev"].map(anciens.groupby("id_ev").size()).fillna(0)
n_nouv = ev["id_ev"].map(nouveaux.groupby("id_ev").size()).fillna(0)
info(f"points d'entrée : {len(anciens)} (règle précédente, voie par voie) -> {len(nouveaux)} (règle corrigée, chemins reliés)")
info(f"médiane par espace (espaces avec entrée) : {n_anc[n_anc > 0].median():.0f} -> {n_nouv[n_nouv > 0].median():.0f}")
bascule = ev[n_nouv == 0]
gagnent = ev[(n_anc == 0) & (n_nouv > 0)]
info(f"espaces qui RETROUVENT des entrées ponctuelles grâce aux chemins reliés : {len(gagnent)}, {gagnent['ha'].sum():.1f} ha")
info(f"espaces SANS entrée ponctuelle avec la règle corrigée (diffus ou injoignable) : {len(bascule)}, "
     f"{bascule['ha'].sum():.1f} ha ; par sous-type : {bascule['subtype_f'].value_counts().to_dict()}")
grands = bascule[bascule["ha"] >= 1].sort_values("ha", ascending=False)
if len(grands):
    print("[parmi eux, les espaces de 1 ha ou plus]")
    print(grands[["name_f", "subtype_f", "ha"]].round(1).to_string(index=False))

# --- 3. Export des témoins et des grands espaces qui basculent, pour le contrôle visuel ---
print("\n--- Témoins exportés ---")
noms = ev["name_f"].fillna("").str.lower()          # noms manquants -> texte vide (pas de NaN)
temoins = ev[noms.apply(lambda n: any(t.lower() in n for t in TEMOINS))].copy()
for t in TEMOINS:
    trouves = temoins[temoins["name_f"].fillna("").str.lower().str.contains(t.lower(), regex=False)]
    info(f"« {t} » : {len(trouves)} objet(s) {list(trouves['name_f'])} ; entrées "
         f"{int(n_anc[trouves.index].sum())} (avant) -> {int(n_nouv[trouves.index].sum())} (corrigée)")
temoins["groupe"] = "témoin"
grands_b = ev.loc[grands.index].assign(groupe="sans entrée >= 1 ha")
espaces = gpd.GeoDataFrame(pd.concat([temoins, grands_b]).drop_duplicates("id_ev"), crs=ev.crs)
espaces["entrees_avant"] = n_anc[espaces.index].astype(int).values
espaces["entrees_apres"] = n_nouv[espaces.index].astype(int).values
if espaces.empty:
    sys.exit("FAIL  aucun espace à exporter : change les noms de TEMOINS en tête du script")

# Voies EXCLUES par la règle piétonne qui touchent ces espaces : pourquoi aucune voie n'y entre ?
zone = espaces.geometry.buffer(MARGE_RESEAU_M).union_all()
exclues = osm[osm["raison"].notna() & osm.intersects(espaces.geometry.union_all())]
print("\n[voies exclues qui touchent les espaces exportés : km par raison]")
print((exclues.groupby("raison")["longueur"].sum() / 1000).round(2).to_string())

config.AUDIT.mkdir(parents=True, exist_ok=True)
espaces[["id_ev", "groupe", "name_f", "subtype_f", "ha", "entrees_avant", "entrees_apres", "geometry"]] \
    .to_file(SORTIE, layer="espaces", driver="GPKG")
anciens[anciens["id_ev"].isin(espaces["id_ev"])].to_file(SORTIE, layer="entrees_avant", driver="GPKG")
nouveaux[nouveaux["id_ev"].isin(espaces["id_ev"])].to_file(SORTIE, layer="entrees_apres", driver="GPKG")
reseau[reseau.intersects(zone)][["osm_id", "highway", "name", "geometry"]].to_file(SORTIE, layer="reseau", driver="GPKG")
exclues[["osm_id", "highway", "name", "access", "foot", "raison", "geometry"]] \
    .to_file(SORTIE, layer="voies_exclues", driver="GPKG")
info(f"écrit : {SORTIE.relative_to(RACINE)} ; couches espaces ({len(espaces)}), entrees_avant, "
     f"entrees_apres, reseau, voies_exclues ; EPSG:31370")
print("\nFin du contrôle.")

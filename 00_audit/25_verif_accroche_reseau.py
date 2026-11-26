# 25_verif_accroche_reseau.py — contrôle en LECTURE SEULE de la distance « porte → rue » (phase 2, étape 2.5)
# Pour chaque point de population (unités d'adresse + pseudo-points, outils_population), distance au point
# le plus proche du réseau piéton final (outils_reseau). Sert à fixer la distance d'accroche maximale.
# Aucun croisement avec la chaleur ni avec les espaces verts. N'écrit rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\25_verif_accroche_reseau.py > data\travail\bruxelles\audit\25_sortie.txt

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et les modules partagés
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_population import repartir_population
from outils_reseau import lire_voies_osm, ajouter_blocs

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

SEUILS_M = [10, 25, 50, 100, 200]


def info(message):
    print(f"INFO  {message}")


# --- 1. Points de population et réseau final ---
points, _, _, _ = repartir_population(config)
osm, _ = lire_voies_osm(config.DATA_BRUT / "reseau" / "osm_highway_20261101.json", config.CRS_CALCUL)
garde = osm[osm["raison"].isna()].copy()
principal = ajouter_blocs(garde)          # ajoute la colonne « bloc »
reseau = garde[garde["bloc"] == principal][["geometry"]].reset_index(drop=True)
info(f"{len(points)} points de population ({points['pop'].sum():,.0f} hab.) ; réseau : {len(reseau)} voies")

# --- 2. Distance au réseau ---
proche = gpd.sjoin_nearest(points[["pop", "type", "cd_sector", "geometry"]], reseau, distance_col="d_reseau_m")
proche = proche[~proche.index.duplicated()]
d, pop = proche["d_reseau_m"], proche["pop"]

print("\n--- Distance au réseau (m) ---")
print("[par point]")
print(d.describe(percentiles=[0.5, 0.9, 0.99, 0.999]).round(1).to_string())
ordre = np.argsort(d.values)
cumul = np.cumsum(pop.values[ordre]) / pop.sum()
mediane_pond = d.values[ordre][np.searchsorted(cumul, 0.5)]
p99_pond = d.values[ordre][np.searchsorted(cumul, 0.99)]
info(f"pondéré par la population : médiane {mediane_pond:.1f} m, p99 {p99_pond:.1f} m")

print("[population à plus de X m de toute voie]")
for s in SEUILS_M:
    loin = d > s
    print(f"        > {s:4d} m : {loin.sum():7d} points, {pop[loin].sum():10,.0f} hab. ({pop[loin].sum() / pop.sum():.3%})")

print("\n[les 15 points les plus éloignés du réseau : à regarder]")
loin = proche.sort_values("d_reseau_m", ascending=False).head(15)
wgs = loin.to_crs(4326)
for (_, l), g in zip(loin.iterrows(), wgs.geometry):
    print(f"        {l['d_reseau_m']:6.0f} m  {l['pop']:6.1f} hab.  {l['type']:<13} secteur {l['cd_sector']}  "
          f"https://www.google.com/maps?q={g.y:.5f},{g.x:.5f}")

print("\nFin du contrôle (lecture seule, aucun fichier écrit).")

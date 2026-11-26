# 23_audit_adresses.py — audit en LECTURE SEULE des adresses UrbIS comme « unités » pour placer la population
# (phase 2, étape 2.4). Critères fixés le 24/11/2026, avant d'ouvrir le fichier téléchargé.
# Unité = une adresse sans boîte (maison, commerce…) OU une boîte (appartement, bureau…).
# Une adresse « parent » qui a des boîtes n'est pas une unité : ce sont ses boîtes qui comptent.
# Ne crée, ne modifie et n'écrit rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\23_audit_adresses.py > data\travail\bruxelles\audit\23_sortie.txt

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from scipy.stats import spearmanr

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

FICHIERS = sorted((config.DATA_BRUT / "urbis_adresses").glob("urbis_adresses_*.csv"))
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"
FICHIER_GRILLE = config.DATA_BRUT / "statbel" / "grille_2025" / "POP_GRID_2025_3035.geojson"

# Critères (fixés avant les données)
LOGEMENTS_2024 = 606_400                  # Bruxelles Environnement, logements début 2024
UNITES_MIN, UNITES_MAX = 0.7 * LOGEMENTS_2024, 1.5 * LOGEMENTS_2024
MIN_DANS_REGION = 0.99
MIN_SPEARMAN = 0.7                        # unités ~ population, mailles de 125 m
MAX_POP_SANS_UNITE = 0.01                 # part de la population dans des mailles sans aucune unité

pd.set_option("display.width", 200)
resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    print(f"INFO  {message}")


# --- 1. Structure : adresses « parent » et boîtes ---
print("--- 1. Structure du fichier ---")
if not FICHIERS:
    sys.exit("FAIL  aucun fichier urbis_adresses_*.csv : lance d'abord le script 22")
fichier = FICHIERS[-1]
a = pd.read_csv(fichier, dtype=str)
info(f"{fichier.name} : {len(a)} lignes, colonnes {list(a.columns)}")
note(a["INSPIRE_ID"].is_unique, "identifiants uniques")
parents = a[a["PARENTID"].isna()]
boites = a[a["PARENTID"].notna()]
info(f"adresses sans parent : {len(parents)} ; boîtes (avec PARENTID) : {len(boites)}")
info(f"boîtes sans numéro : {boites['BOXNUMBER'].isna().sum()} ; adresses sans parent mais avec numéro de boîte : "
     f"{parents['BOXNUMBER'].notna().sum()}")
orphelines = ~boites["PARENTID"].isin(a["INSPIRE_ID"])
info(f"boîtes dont le parent est introuvable : {orphelines.sum()}")
n_boites = boites.groupby("PARENTID").size()
info(f"adresses avec boîtes : {len(n_boites)} ; boîtes par adresse : médiane {n_boites.median():.0f}, "
     f"p99 {n_boites.quantile(0.99):.0f}, max {n_boites.max()}")

# --- 2. Unités ---
print("\n--- 2. Unités ---")
unites = pd.concat([parents[~parents["INSPIRE_ID"].isin(n_boites.index)], boites])
note(UNITES_MIN <= len(unites) <= UNITES_MAX,
     f"{len(unites)} unités ({len(unites) / LOGEMENTS_2024:.2f} × les {LOGEMENTS_2024:,} logements de 2024 ; "
     f"attendu entre 0,7 et 1,5)")
prefixes = boites["BOXNUMBER"].str.extract(r"^([A-Za-z]+)")[0].str.lower().value_counts()
info(f"préfixes des numéros de boîte (15 premiers) : {prefixes.head(15).to_dict()}")

pts = gpd.GeoDataFrame(unites, geometry=gpd.points_from_xy(unites["XL72"].astype(float),
                                                            unites["YL72"].astype(float)), crs=31370)
region = gpd.read_file(FICHIER_REGION).to_crs(31370)
dedans = pts.within(region.geometry.union_all())
note(dedans.mean() >= MIN_DANS_REGION, f"unités dans la Région : {dedans.mean():.2%} (min {MIN_DANS_REGION:.0%})")
pts = pts[dedans]

par_point = pts.groupby(["XL72", "YL72"]).size().sort_values(ascending=False)
info(f"points distincts : {len(par_point)} ; unités par point : médiane {par_point.median():.0f}, "
     f"p90 {par_point.quantile(0.9):.0f}, p99 {par_point.quantile(0.99):.0f}")
print("[les 8 points qui portent le plus d'unités : à regarder (résidence, hôpital, bureaux ?)]")
for (x, y), n in par_point.head(8).items():
    lon, lat = gpd.GeoSeries(gpd.points_from_xy([float(x)], [float(y)]), crs=31370).to_crs(4326).iloc[0].coords[0]
    secteur = pts.loc[(pts["XL72"] == x) & (pts["YL72"] == y), "STATNISCODE"].iloc[0]
    print(f"        {n:5d} unités  secteur {secteur}  https://www.google.com/maps?q={lat:.5f},{lon:.5f}")

# --- 3. Cohérence avec la population (grille Statbel 2025) ---
print("\n--- 3. Cohérence avec la population ---")
grille = gpd.read_file(FICHIER_GRILLE, bbox=region)
grille = grille[grille.geometry.centroid.within(region.to_crs(grille.crs).geometry.union_all())].copy()
grille["id_maille"] = range(len(grille))
lien = gpd.sjoin(pts.to_crs(grille.crs)[["geometry"]], grille[["id_maille", "geometry"]], predicate="within")
grille["unites"] = grille["id_maille"].map(lien.groupby("id_maille").size()).fillna(0)
info(f"{len(grille)} mailles habitées dans la Région ; unités hors de toute maille habitée : "
     f"{len(pts) - len(lien)} ({(len(pts) - len(lien)) / len(pts):.1%}) — bureaux, commerces, mailles vides")

fines = grille[grille["ms_len"].astype(int) == 125]
rho, _ = spearmanr(fines["unites"], fines["ms_pop"])
note(rho >= MIN_SPEARMAN, f"Spearman unités ~ population, {len(fines)} mailles de 125 m : {rho:.3f} (min {MIN_SPEARMAN})")
for taille in (250, 500, 1000):
    m = grille[grille["ms_len"].astype(int) == taille]
    if len(m) > 2:
        info(f"Spearman, mailles de {taille} m ({len(m)}) : {spearmanr(m['unites'], m['ms_pop'])[0]:.3f}")

pop = grille["ms_pop"].astype(float)
sans = grille["unites"] == 0
note(pop[sans].sum() / pop.sum() <= MAX_POP_SANS_UNITE,
     f"population dans des mailles sans aucune unité : {pop[sans].sum():,.0f} hab. "
     f"({pop[sans].sum() / pop.sum():.2%}, max {MAX_POP_SANS_UNITE:.0%}) ; {sans.sum()} mailles")
grille["hab_par_unite"] = pop / grille["unites"].where(grille["unites"] > 0)
print("[habitants par unité, par taille de maille (médiane)]")
print(grille.groupby(grille["ms_len"].astype(int))["hab_par_unite"].median().round(2).to_string())

print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")

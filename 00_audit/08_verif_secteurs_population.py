# 08_verif_secteurs_population.py
# Contrôle en LECTURE SEULE des fichiers Statbel téléchargés par 01_acquisition/07_telecharger_statbel.py :
# secteurs au 01/01/2026, population par secteur 2026 et 2025 « NEW », grille de population 2025.
# Critères fixés avant les données (journal, 20/11/2026). Aucun fichier écrit.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\08_verif_secteurs_population.py

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

DOSSIER = config.DATA_BRUT / "statbel"
FICHIER_SECTEURS = DOSSIER / "secteurs_2026" / "sh_statbel_statistical_sectors_31370_20260101.geojson" / "sh_statbel_statistical_sectors_31370_20260101.geojson"
FICHIER_POP_2026 = DOSSIER / "population_2026" / "OPENDATA_SECTOREN_2026.txt"
FICHIER_POP_2025 = DOSSIER / "population_2025_new" / "OPENDATA_SECTOREN_2025_NEW.txt"
FICHIER_GRILLE = DOSSIER / "grille_2025" / "POP_GRID_2025_3035.geojson"
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"

CODE_REGION = "04000"                  # code NIS de la Région de Bruxelles-Capitale
N_SECTEURS_ATTENDU = 749               # IBSA, communiqué du 17/12/2025
N_COMMUNES_ATTENDU = 19
SURFACE_URBIS_KM2 = 162.42             # contour UrbIS (audit 03)
POP_OFFICIELLE = {2026: 1_255_834, 2025: 1_255_795}   # Statbel (Be.STAT), Région au 1er janvier
TOLERANCE_POP = 0.005                  # 0,5 %
TOLERANCE_GRILLE = 0.03                # 3 %
TAILLES_MAILLES = {125, 250, 500, 1000}
SEUIL_PEU_PEUPLE = 50                  # pour information seulement (seuil fixé en phase 2)

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


# --- 1. Limites des secteurs 2026 ---
print("--- Secteurs au 01/01/2026 ---")
colonnes = ["cd_sector", "cd_munty_refnis", "tx_munty_descr_fr", "cd_rgn_refnis", "ms_area_ha", "dt_situation"]
secteurs = gpd.read_file(FICHIER_SECTEURS, columns=colonnes)
# Codes lus comme du TEXTE : on refait les zéros de tête au cas où un code aurait été lu comme un nombre
secteurs["cd_rgn_refnis"] = secteurs["cd_rgn_refnis"].astype(str).str.zfill(5)
secteurs["cd_munty_refnis"] = secteurs["cd_munty_refnis"].astype(str).str.zfill(5)
secteurs["cd_sector"] = secteurs["cd_sector"].astype(str)
note(secteurs.crs.to_epsg() == 31370, f"CRS : EPSG:{secteurs.crs.to_epsg()} (attendu 31370)")
print(f"INFO  date de situation : {sorted(secteurs['dt_situation'].astype(str).unique())}")

bxl = secteurs[secteurs["cd_rgn_refnis"] == CODE_REGION].copy()
note(len(bxl) == N_SECTEURS_ATTENDU, f"{len(bxl)} secteurs à Bruxelles (attendu {N_SECTEURS_ATTENDU}, nouveau découpage)")
n_communes = bxl["cd_munty_refnis"].nunique()
note(n_communes == N_COMMUNES_ATTENDU, f"{n_communes} communes (attendu {N_COMMUNES_ATTENDU})")
note(not bxl["cd_sector"].duplicated().any(), "aucun code de secteur en double")
n_invalides = (~bxl.is_valid).sum()
note(n_invalides == 0, f"géométries valides ({n_invalides} invalides)")

surface_km2 = bxl.area.sum() / 1e6
note(abs(surface_km2 - SURFACE_URBIS_KM2) / SURFACE_URBIS_KM2 <= 0.01,
     f"surface totale des secteurs : {surface_km2:.2f} km² (UrbIS : {SURFACE_URBIS_KM2}, écart max 1 %)")
print(f"INFO  surface déclarée (ms_area_ha) : {bxl['ms_area_ha'].sum() / 100:.2f} km²")

region = gpd.read_file(FICHIER_REGION).to_crs(31370)
union_secteurs = bxl.geometry.union_all()
desaccord_km2 = union_secteurs.symmetric_difference(region.geometry.union_all()).area / 1e6
note(desaccord_km2 / SURFACE_URBIS_KM2 <= 0.01,
     f"zone de désaccord entre secteurs et contour UrbIS : {desaccord_km2:.3f} km² ({100 * desaccord_km2 / SURFACE_URBIS_KM2:.2f} %, max 1 %)")


# --- 2. Population par secteur ---
def lire_population(fichier, encodage):
    """Lit un fichier de population Statbel (séparateur |), codes en texte, et garde Bruxelles."""
    pop = pd.read_csv(fichier, sep="|", encoding=encodage, dtype={"CD_REFNIS": str, "CD_SECTOR": str})
    pop["CD_REFNIS"] = pop["CD_REFNIS"].str.zfill(5)
    return pop[pop["CD_REFNIS"].str.startswith("21")].copy()   # communes bruxelloises : NIS 21xxx


codes_secteurs = set(bxl["cd_sector"])
populations = {}
for annee, fichier, encodage in [(2026, FICHIER_POP_2026, "utf-8-sig"), (2025, FICHIER_POP_2025, "latin-1")]:
    print(f"\n--- Population par secteur {annee} ---")
    pop = lire_population(fichier, encodage)
    populations[annee] = pop
    note(not pop["CD_SECTOR"].duplicated().any(), f"{len(pop)} lignes bruxelloises, aucun code en double")
    note(pop["TOTAL"].notna().all() and (pop["TOTAL"] >= 0).all(), "population renseignée et ≥ 0 partout")

    hors_limites = pop[~pop["CD_SECTOR"].isin(codes_secteurs)]
    inconnus = hors_limites[hors_limites["CD_SECTOR"].str.contains("ZZZZ")]   # « secteur inconnu » chez Statbel
    autres = hors_limites[~hors_limites["CD_SECTOR"].str.contains("ZZZZ")]
    print(f"INFO  secteurs « inconnus » (ZZZZ) : {len(inconnus)} lignes, {inconnus['TOTAL'].sum()} habitants")
    note(len(autres) == 0, f"tous les codes de population existent dans les limites 2026 ({len(autres)} absents)"
         + (f" : {autres['CD_SECTOR'].head(10).tolist()}" if len(autres) else ""))
    sans_pop = codes_secteurs - set(pop["CD_SECTOR"])
    print(f"INFO  secteurs des limites sans ligne de population : {len(sans_pop)}")

    total = pop["TOTAL"].sum()
    officiel = POP_OFFICIELLE[annee]
    note(abs(total - officiel) / officiel <= TOLERANCE_POP,
         f"population totale : {total:,} (officiel {officiel:,}, écart {100 * (total - officiel) / officiel:+.2f} %, max 0,5 %)")

# Cohérence d'une année sur l'autre
print("\n--- Cohérence 2025 → 2026 ---")
duo = populations[2025][["CD_SECTOR", "TOTAL"]].merge(populations[2026][["CD_SECTOR", "TOTAL"]],
                                                      on="CD_SECTOR", how="outer", suffixes=("_2025", "_2026"))
print(f"INFO  secteurs présents une seule année : {duo.isna().any(axis=1).sum()}")
duo = duo.dropna()
variation_totale = duo["TOTAL_2026"].sum() / duo["TOTAL_2025"].sum() - 1
note(abs(variation_totale) <= 0.03, f"variation de la population totale : {100 * variation_totale:+.2f} % (max ±3 %)")
peuples = duo[duo["TOTAL_2025"] >= SEUIL_PEU_PEUPLE]
forte = (abs(peuples["TOTAL_2026"] / peuples["TOTAL_2025"] - 1) > 0.20).sum()
print(f"INFO  secteurs de ≥ {SEUIL_PEU_PEUPLE} habitants qui varient de plus de 20 % : {forte} sur {len(peuples)}")
print(f"INFO  corrélation des populations 2025 et 2026 par secteur : {np.corrcoef(duo['TOTAL_2025'], duo['TOTAL_2026'])[0, 1]:.4f}")

# Secteurs peu peuplés (pour la phase 2)
pop26 = bxl[["cd_sector"]].merge(populations[2026][["CD_SECTOR", "TOTAL"]], left_on="cd_sector",
                                  right_on="CD_SECTOR", how="left")["TOTAL"].fillna(0)
peu = pop26 < SEUIL_PEU_PEUPLE
print(f"INFO  secteurs de moins de {SEUIL_PEU_PEUPLE} habitants : {peu.sum()} (dont {(pop26 == 0).sum()} à 0), "
      f"soit {100 * pop26[peu].sum() / pop26.sum():.2f} % de la population")

# --- 3. Grille de population à cellules variables (01/01/2025) ---
print("\n--- Grille de population 2025 ---")
region_3035 = region.to_crs(3035)
grille = gpd.read_file(FICHIER_GRILLE, bbox=tuple(region_3035.total_bounds))   # seulement autour de Bruxelles
note(grille.crs.to_epsg() == 3035, f"CRS : EPSG:{grille.crs.to_epsg()} (attendu 3035)")
tailles = {int(t) for t in grille["ms_len"].unique()}
note(tailles <= TAILLES_MAILLES, f"tailles de mailles : {sorted(tailles)} (attendu parmi 125, 250, 500, 1000 m)")
# Une maille est rattachée à la Région si son centre est dedans
centres = grille.geometry.centroid
dans = centres.within(region_3035.geometry.union_all())
pop_grille = grille.loc[dans, "ms_pop"].sum()
pop_2025 = populations[2025]["TOTAL"].sum()
note(abs(pop_grille - pop_2025) / pop_2025 <= TOLERANCE_GRILLE,
     f"population des mailles de la Région : {pop_grille:,} (secteurs 2025 : {pop_2025:,}, "
     f"écart {100 * (pop_grille - pop_2025) / pop_2025:+.2f} %, max 3 %)")
print("INFO  répartition de la population bruxelloise par taille de maille :")
for taille, part in (grille.loc[dans].groupby("ms_len")["ms_pop"].sum() / pop_grille * 100).items():
    n = (grille.loc[dans, "ms_len"] == taille).sum()
    print(f"        {taille:>5} m : {n:5} mailles, {part:5.1f} % de la population")

# --- 4. Classes d'âge ---
print("\nINFO  aucune colonne d'âge dans la population par secteur ni dans la grille (inspection du script 07)")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

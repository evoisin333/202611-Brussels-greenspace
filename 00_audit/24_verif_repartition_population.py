# 24_verif_repartition_population.py — contrôle en LECTURE SEULE de la répartition de la population
# sur les unités d'adresse (phase 2, étape 2.4). La règle est dans outils_population.py ; elle est
# appliquée EN MÉMOIRE. Critères fixés le 26/11/2026, avant le premier calcul. N'écrit rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\24_verif_repartition_population.py > data\travail\bruxelles\audit\24_sortie.txt

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from scipy.stats import spearmanr

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et les modules partagés
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_population import repartir_population

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

POP_OFFICIELLE_2026 = 1_255_834            # Statbel, Région au 1er janvier 2026 (audit 08)
MAX_ECART_SECTEUR = 0.5                    # habitants
MIN_SPEARMAN_MAILLES = 0.9                 # population replacée ~ grille, mailles de 125 m
resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    print(f"INFO  {message}")


seuil = getattr(config, "SEUIL_POP_SECTEUR", None)
if seuil is None:
    sys.exit("FAIL  SEUIL_POP_SECTEUR absent de config.py : ajoute le bloc « Population »")

# --- 1. Répartition (en mémoire) et cas particuliers ---
print("--- 1. Répartition et cas particuliers ---")
points, diag, pop_secteur, grille = repartir_population(config)
for cle, valeur in diag.items():
    info(f"{cle} : {valeur:,.0f}" if isinstance(valeur, float) else f"{cle} : {valeur}")
print("[points par type : nombre et habitants]")
print(points.groupby("type")["pop"].agg(points="size", habitants="sum").round(0).to_string())

# --- 2. Totaux ---
print("\n--- 2. Totaux ---")
note((points["pop"] >= 0).all(), "aucune population négative")
par_secteur = points.groupby("cd_sector")["pop"].sum()
connus = pop_secteur[~pop_secteur.index.str.contains("ZZZZ")]
ecart = (par_secteur.reindex(connus.index, fill_value=0) - connus).abs()
note(ecart.max() <= MAX_ECART_SECTEUR,
     f"somme par secteur = Statbel 2026 : écart maximal {ecart.max():.4f} hab. (max {MAX_ECART_SECTEUR}) sur {len(connus)} secteurs")
attendu = POP_OFFICIELLE_2026 - diag["zzzz_habitants"]
note(abs(points["pop"].sum() - attendu) <= MAX_ECART_SECTEUR,
     f"total placé : {points['pop'].sum():,.1f} hab. (officiel {POP_OFFICIELLE_2026:,} − ZZZZ {diag['zzzz_habitants']:,.0f} = {attendu:,.0f})")
hors = set(par_secteur.index) - set(connus.index)
note(not hors, f"aucun point dans un secteur absent de la population Statbel ({len(hors)})")

# --- 3. Cohérence avec la grille ---
print("\n--- 3. Cohérence avec la grille ---")
lien = gpd.sjoin(points.to_crs(grille.crs)[["pop", "geometry"]], grille[["id_maille", "geometry"]], predicate="within")
lien = lien[~lien.index.duplicated()]
grille["pop_placee"] = grille["id_maille"].map(lien.groupby("id_maille")["pop"].sum()).fillna(0)
fines = grille[grille["ms_len"].astype(int) == 125]
rho = spearmanr(fines["pop_placee"], fines["ms_pop"])[0]
note(rho >= MIN_SPEARMAN_MAILLES, f"Spearman population placée ~ grille 2025, {len(fines)} mailles de 125 m : {rho:.3f} (min {MIN_SPEARMAN_MAILLES})")
diff = (grille["pop_placee"] - grille["ms_pop"]).abs()
info(f"écart absolu par maille (placé 2026 vs grille 2025) : médiane {diff.median():.1f}, p95 {diff.quantile(0.95):.1f} hab.")

# --- 4. Seuil minimal de population par secteur (pour les statistiques) ---
print("\n--- 4. Seuil minimal de population par secteur ---")
petits = connus[connus < seuil]
info(f"secteurs de moins de {seuil} habitants : {len(petits)} ({petits.sum():,.0f} hab., "
     f"{petits.sum() / connus.sum():.2%} de la population) — exclus des statistiques, gardés dans les totaux")

print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")

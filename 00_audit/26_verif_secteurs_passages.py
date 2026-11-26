# 26_verif_secteurs_passages.py — contrôle en LECTURE SEULE avant de figer la méthode « chaleur » (étape 2.6)
# 1. Taille des secteurs face aux pixels thermiques : nombre de pixels Landsat (grille 30 m du passage test)
#    dont le centre tombe dans chaque secteur, hors eau. Règle proposée : >= 20 pixels clairs par passage.
# 2. Répartition des 24 passages clairs par mois et par été (audit 04), pour le critère de comparaison des mois.
# Aucune température n'est lue (QA_PIXEL seulement). N'écrit rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\26_verif_secteurs_passages.py > data\travail\bruxelles\audit\26_sortie.txt

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rioxarray
from rioxarray.merge import merge_arrays
from rasterio.features import rasterize

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et les modules partagés
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_population import charger_secteurs, charger_population

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

MIN_PIXELS = 20                    # ≈ 1,8 ha à 30 m, soit ~2 « vrais » pixels thermiques de 100 m
SEUIL_CLAIR = 0.90                 # passage retenu si >= 90 % de la Région est claire (audit 04)
MIN_PASSAGES_MOIS, MIN_ETES = 5, 3 # critère de comparaison des mois (journal, 23/11/2026)
BIT_REMPLISSAGE, BIT_EAU = 1 << 0, 1 << 7


def info(message):
    print(f"INFO  {message}")


# --- 1. Pixels par secteur (grille du passage test) ---
print("--- 1. Taille des secteurs face aux pixels Landsat ---")
qa_fichiers = sorted((config.DATA_BRUT / "landsat_test").glob("*_qa_pixel.tif"))
couches = []
for f in qa_fichiers:
    r = rioxarray.open_rasterio(f, masked=False).squeeze()
    couches.append(r.rio.write_nodata(1))            # 1 = « fill » : sans ça, l'assemblage garde une seule scène (bug 1.4)
qa = merge_arrays(couches) if len(couches) > 1 else couches[0]
valeurs = qa.values.astype(np.int64)
terre = ((valeurs & BIT_REMPLISSAGE) == 0) & ((valeurs & BIT_EAU) == 0)
info(f"{len(qa_fichiers)} scène(s) assemblée(s) ; grille {qa.rio.crs}, {qa.shape[1]} × {qa.shape[0]} pixels")

secteurs = charger_secteurs(config).to_crs(qa.rio.crs)
pop = charger_population(config)
secteurs["pop"] = secteurs["cd_sector"].map(pop).fillna(0)
ids = rasterize(((g, i + 1) for i, g in enumerate(secteurs.geometry)), out_shape=valeurs.shape,
                transform=qa.rio.transform(), fill=0, all_touched=False, dtype="int32")
n_tout = np.bincount(ids.ravel(), minlength=len(secteurs) + 1)[1:]
n_terre = np.bincount(ids[terre].ravel(), minlength=len(secteurs) + 1)[1:]
secteurs["pixels"], secteurs["pixels_terre"] = n_tout, n_terre

habites = secteurs[secteurs["pop"] >= config.SEUIL_POP_SECTEUR]
info(f"secteurs habités (>= {config.SEUIL_POP_SECTEUR} hab.) : {len(habites)}")
print("[pixels de terre par secteur habité]")
print(habites["pixels_terre"].describe(percentiles=[0.01, 0.05, 0.1, 0.5]).round(0).to_string())
for seuil in (10, MIN_PIXELS, 30, 50):
    petits = habites[habites["pixels_terre"] < seuil]
    info(f"< {seuil:2d} pixels de terre (≈ {seuil * 0.09:.1f} ha) : {len(petits)} secteurs, "
         f"{petits['pop'].sum():,.0f} hab. ({petits['pop'].sum() / habites['pop'].sum():.2%})")
print(f"[secteurs habités sous {MIN_PIXELS} pixels : les 15 plus peuplés]")
print(habites[habites["pixels_terre"] < MIN_PIXELS].sort_values("pop", ascending=False)
      [["cd_sector", "pop", "pixels", "pixels_terre"]].head(15).to_string(index=False))

# --- 2. Passages clairs par mois et par été ---
print("\n--- 2. Passages clairs par mois et par été (audit 04) ---")
fichier = config.AUDIT / "04_part_claire_passages.csv"
p = pd.read_csv(fichier, sep=None, engine="python")
info(f"{fichier.name} : colonnes {list(p.columns)}")
col_date = next((c for c in p.columns if "date" in c.lower()), None)
col_part = next((c for c in p.columns if "clair" in c.lower() or "part" in c.lower()), None)
if col_date is None or col_part is None:
    sys.exit("FAIL  colonnes de date ou de part claire introuvables : colle-moi cette sortie")
p["date"] = pd.to_datetime(p[col_date])
part = pd.to_numeric(p[col_part].astype(str).str.replace(",", "."), errors="coerce")
part = part / 100 if part.max() > 1 else part
col_tier = next((c for c in p.columns if "tier" in c.lower() or "categ" in c.lower()), None)
garde = (part >= SEUIL_CLAIR) & p["date"].dt.year.isin(config.ANNEES)
if col_tier:
    garde &= p[col_tier].astype(str).str.upper().str.contains("T1")
clairs = p[garde].drop_duplicates("date")
info(f"passages clairs retenus : {len(clairs)} (attendu : 24, audit 04)")
tableau = pd.crosstab(clairs["date"].dt.year, clairs["date"].dt.month.map({6: "juin", 7: "juillet", 8: "août"}))
print(tableau.to_string())


def critere(dates, nom):
    n, etes = len(dates), dates.dt.year.nunique()
    ok = n >= MIN_PASSAGES_MOIS and etes >= MIN_ETES
    info(f"{nom:<16} : {n:2d} passages sur {etes} été(s) -> {'OK' if ok else 'insuffisant'}")
    return ok


mois = clairs["date"].dt.month
par_mois = [critere(clairs.loc[mois == m, "date"], n) for m, n in [(6, "juin"), (7, "juillet"), (8, "août")]]
if all(par_mois):
    info("décision : comparaison juin / juillet / août possible")
else:
    debut = critere(clairs.loc[mois.isin([6, 7]), "date"], "juin-juillet")
    fin = critere(clairs.loc[mois == 8, "date"], "août")
    info("décision : " + ("comparaison début d'été / août" if debut and fin else "pas de comparaison, limite écrite"))

print("\nFin du contrôle (lecture seule, aucun fichier écrit).")

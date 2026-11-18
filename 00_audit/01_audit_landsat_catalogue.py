# 01_audit_landsat_catalogue.py
# Audit du catalogue Landsat (étape 1.1) : MÉTADONNÉES SEULEMENT, aucune image téléchargée.
# Compte les scènes d'été Landsat 8 et 9 qui touchent l'emprise de config.py, année par année.
# Écrit une seule table : data/travail/<ville>/audit/01_landsat_catalogue.csv (format français : ; et ,)
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\01_audit_landsat_catalogue.py

import sys
import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import pystac_client

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

URL_CATALOGUE = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
SATELLITES = ["landsat-8", "landsat-9"]   # Landsat 7 exclu (images à bandes vides depuis 2003)
FICHIER_SORTIE = config.AUDIT / "01_landsat_catalogue.csv"

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


# --- 1. Requête exacte (à recopier dans le README) ---
mois_debut, mois_fin = min(config.MOIS_ETE), max(config.MOIS_ETE)
print("--- Requête ---")
print(f"Catalogue  : {URL_CATALOGUE}")
print(f"Collection : {COLLECTION}")
print(f"Emprise    : {config.EMPRISE_WGS84} (WGS84, lon_min, lat_min, lon_max, lat_max)")
print(f"Années     : {config.ANNEES_AUDIT[0]}-{config.ANNEES_AUDIT[-1]}, mois {mois_debut} à {mois_fin}")
print(f"Date       : {date.today().isoformat()}")

# --- 2. Connexion au catalogue ---
print("\n--- Connexion ---")
try:
    catalogue = pystac_client.Client.open(URL_CATALOGUE)
    note(True, "catalogue joignable")
except Exception as erreur:
    note(False, f"catalogue injoignable ({erreur})")
    sys.exit(1)

# --- 3. Recherche, une année à la fois ---
print("\n--- Recherche ---")
lignes = []
for annee in config.ANNEES_AUDIT:
    dernier_jour = calendar.monthrange(annee, mois_fin)[1]
    periode = f"{annee}-{mois_debut:02d}-01/{annee}-{mois_fin:02d}-{dernier_jour}"
    recherche = catalogue.search(collections=[COLLECTION], bbox=config.EMPRISE_WGS84, datetime=periode)
    n_annee = 0
    for item in recherche.items():
        p = item.properties
        lignes.append({
            "id": item.id,
            "date": p.get("datetime"),
            "annee": annee,
            "satellite": p.get("platform"),
            "wrs_path": p.get("landsat:wrs_path"),
            "wrs_row": p.get("landsat:wrs_row"),
            "nuages_scene_pct": p.get("eo:cloud_cover"),
            "categorie": p.get("landsat:collection_category"),
        })
        n_annee += 1
    print(f"  {annee} : {n_annee} scènes (tous satellites)")

df = pd.DataFrame(lignes)
if df.empty:
    note(False, "aucune scène trouvée : vérifier l'emprise et les dates")
    sys.exit(1)
df["date"] = pd.to_datetime(df["date"], utc=True)

# On garde Landsat 8 et 9 ; on compte ce qui est écarté
autres = df[~df["satellite"].isin(SATELLITES)]
print(f"\nINFO  scènes écartées (autres satellites) : {autres['satellite'].value_counts().to_dict()}")
df = df[df["satellite"].isin(SATELLITES)].copy()

# --- 4. Contrôles de plausibilité ---
print("\n--- Contrôles ---")
note(len(df) > 0, f"{len(df)} scènes Landsat 8/9 au total")
note(df["date"].dt.month.isin(config.MOIS_ETE).all(), "toutes les dates sont en juin-août")
note(not ((df["satellite"] == "landsat-8") & (df["date"] < "2013-03-01")).any(),
     "aucune scène Landsat 8 avant son lancement (février 2013)")
note(not ((df["satellite"] == "landsat-9") & (df["date"] < "2021-09-27")).any(),
     "aucune scène Landsat 9 avant son lancement (septembre 2021)")
note(not df["id"].duplicated().any(), "aucune scène en double")
for colonne in ["wrs_path", "wrs_row", "nuages_scene_pct", "categorie"]:
    n_vides = df[colonne].isna().sum()
    note(n_vides == 0, f"colonne {colonne} remplie ({n_vides} vides)")
for annee in config.ANNEES:
    n = (df["annee"] == annee).sum()
    note(n >= 1, f"été {annee} : {n} scènes Landsat 8/9")

# --- 5. Récapitulatifs ---
print("\n--- Scènes par année et satellite ---")
print(pd.crosstab(df["annee"], df["satellite"], margins=True, margins_name="total"))

print("\n--- Scènes par orbite/ligne WRS-2 ---")
df["path_row"] = df["wrs_path"].astype(str).str.zfill(3) + "/" + df["wrs_row"].astype(str).str.zfill(3)
print(pd.crosstab(df["path_row"], df["satellite"], margins=True, margins_name="total"))

print("\n--- Catégories (T1 = meilleure géométrie) ---")
print(df["categorie"].value_counts(dropna=False).to_string())

print("\n--- Couverture nuageuse de la SCÈNE entière (%), médiane par année ---")
print("    (ce n'est PAS la couverture sur Bruxelles : mesurée à l'étape 1.2)")
print(df.groupby("annee")["nuages_scene_pct"].median().round(0).to_string())

# --- 6. Écriture de la table d'audit ---
config.AUDIT.mkdir(parents=True, exist_ok=True)
df["date"] = df["date"].dt.strftime("%Y-%m-%d")
df["date_requete"] = date.today().isoformat()
df.sort_values("date").to_csv(FICHIER_SORTIE, sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(f"\nTable écrite : {FICHIER_SORTIE.relative_to(RACINE)}")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

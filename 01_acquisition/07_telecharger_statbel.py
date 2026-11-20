# 07_telecharger_statbel.py
# Étape 1.5 : télécharge les fichiers Statbel (secteurs, population, grille) et les décompresse TELS QUELS.
# Puis INSPECTION en lecture seule : colonnes, nombre de lignes, CRS, exemples. Aucun contrôle PASS/FAIL ici :
# les contrôles (script 08) seront écrits avec les vrais noms de colonnes vus dans cette inspection.
# Fichiers nationaux, rangés dans data/brut/<ville>/statbel/. Licence : CC BY 4.0 (citer Statbel).
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\07_telecharger_statbel.py

import sys
import zipfile
from datetime import date
from pathlib import Path

import requests
import pyogrio
import geopandas as gpd

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

BASE = "https://statbel.fgov.be/sites/default/files/files/opendata"
FICHIERS = {
    "secteurs_2026": f"{BASE}/Statistische%20sectoren/sh_statbel_statistical_sectors_31370_20260101.geojson.zip",
    "population_2026": f"{BASE}/bevolking/sectoren/OPENDATA_SECTOREN_2026.zip",
    "population_2025_new": f"{BASE}/bevolking/sectoren/OPENDATA_SECTOREN_2025_NEW.zip",
    "grille_2025": f"{BASE}/SH_VARYING_CELL_SIZE_GRID/POP_GRID_2025_3035_geojson.zip",
}
DOSSIER = config.DATA_BRUT / "statbel"
FICHIER_REQUETE = DOSSIER / "statbel_requetes.txt"

print("--- Téléchargement ---")
print(f"Date : {date.today().isoformat()}")
DOSSIER.mkdir(parents=True, exist_ok=True)
lignes_requete = [f"Date de téléchargement : {date.today().isoformat()}", "Licence : CC BY 4.0 (Statbel)"]

for nom, url in FICHIERS.items():
    fichier_zip = DOSSIER / f"{nom}.zip"
    if fichier_zip.exists():
        print(f"INFO  {fichier_zip.name} déjà présent : pas de nouveau téléchargement (le supprimer pour le refaire)")
    else:
        reponse = requests.get(url, stream=True, timeout=300)
        if reponse.status_code != 200:
            print(f"FAIL  {nom} : téléchargement refusé (code HTTP {reponse.status_code}). URL : {url}")
            sys.exit(1)
        with open(fichier_zip, "wb") as sortie:
            for morceau in reponse.iter_content(chunk_size=1 << 20):   # par blocs de 1 Mo
                sortie.write(morceau)
        print(f"PASS  {nom} : {fichier_zip.stat().st_size / 1e6:.1f} Mo")
    # Un zip valide se termine par un répertoire central : sinon c'est probablement une page web (blocage)
    if not zipfile.is_zipfile(fichier_zip):
        print(f"FAIL  {fichier_zip.name} n'est pas un vrai zip (page de blocage ?). Le supprimer et réessayer.")
        sys.exit(1)
    dossier_extrait = DOSSIER / nom
    with zipfile.ZipFile(fichier_zip) as archive:
        archive.extractall(dossier_extrait)
    lignes_requete.append(f"{nom} : {url}")

FICHIER_REQUETE.write_text("\n".join(lignes_requete) + "\n", encoding="utf-8")
print(f"Requêtes notées : {FICHIER_REQUETE.relative_to(RACINE)}")


# --- Inspection en lecture seule ---
def lire_debut_texte(chemin, n=3):
    """Renvoie les n premières lignes d'un fichier texte, en essayant deux encodages."""
    for encodage in ["utf-8-sig", "latin-1"]:
        try:
            with open(chemin, encoding=encodage) as f:
                return [next(f).rstrip("\n") for _ in range(n)], encodage
        except (UnicodeDecodeError, StopIteration):
            continue
    return [], "inconnu"


def lignes_bruxelloises(chemin, encodage, n=2):
    """Renvoie les n premières lignes qui contiennent le code NIS de Bruxelles-Ville (21004)."""
    trouvees = []
    with open(chemin, encoding=encodage) as f:
        for ligne in f:
            if "21004" in ligne:
                trouvees.append(ligne.rstrip("\n"))
                if len(trouvees) == n:
                    break
    return trouvees


for nom in FICHIERS:
    print(f"\n=== {nom} ===")
    for chemin in sorted((DOSSIER / nom).rglob("*")):
        if chemin.is_dir():
            continue
        print(f"Fichier : {chemin.relative_to(DOSSIER)} ({chemin.stat().st_size / 1e6:.1f} Mo)")
        extension = chemin.suffix.lower()
        if extension in [".geojson", ".json", ".gpkg", ".shp", ".sqlite"]:
            infos = pyogrio.read_info(chemin)
            print(f"  entités : {infos['features']}, CRS : {infos['crs']}")
            print(f"  colonnes : {list(infos['fields'])}")
            exemple = gpd.read_file(chemin, max_features=3)
            print(exemple.drop(columns="geometry").to_string())
        elif extension in [".txt", ".csv"]:
            debut, encodage = lire_debut_texte(chemin)
            print(f"  encodage : {encodage}")
            print("  premières lignes :")
            for ligne in debut:
                print(f"    {ligne}")
            print("  lignes contenant 21004 (Bruxelles-Ville) :")
            for ligne in lignes_bruxelloises(chemin, encodage):
                print(f"    {ligne}")
        elif extension == ".xlsx":
            print("  fichier Excel : non inspecté ici (on utilise le TXT)")

print("\nColle toute cette sortie : le script 08 sera écrit avec les vrais noms de colonnes.")

# 00_verif_environnement.py
# Contrôle en lecture seule de l'environnement et de la configuration du dépôt.
# Ne crée, ne modifie et ne télécharge rien. Imprime une ligne PASS / FAIL / INFO par contrôle.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\00_verif_environnement.py

import sys
from pathlib import Path
from importlib import import_module

# Le script est dans 00_audit/ : on ajoute la racine du dépôt au chemin pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

resultats = []  # liste de (statut, message)


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    """Affiche une information qui n'est ni une réussite ni un échec."""
    print(f"INFO  {message}")


# --- 1. Python et environnement conda ---
print("\n--- Python et environnement ---")
version = sys.version_info
note(version[:2] == (3, 11), f"Python {version.major}.{version.minor}.{version.micro} (attendu : 3.11)")
note(Path(sys.prefix).name == "chaleur", f"environnement actif : {sys.prefix} (attendu : ...\\chaleur)")

# --- 2. Paquets ---
print("\n--- Paquets ---")
paquets = ["geopandas", "rioxarray", "pystac_client", "planetary_computer", "owslib",
           "openpyxl", "requests", "matplotlib", "scipy", "sqlalchemy", "psycopg2",
           "geoalchemy2", "esda", "libpysal"]
for nom in paquets:
    try:
        module = import_module(nom)
        note(True, f"{nom} {getattr(module, '__version__', '(version non lue)')}")
    except Exception as erreur:
        note(False, f"{nom} : import impossible ({erreur})")

# --- 3. Configuration ---
print("\n--- config.py ---")
try:
    import config
    note(True, "config.py lu")
except Exception as erreur:
    note(False, f"config.py illisible ({erreur})")
    config = None

if config is not None:
    note(bool(config.VILLE), f"VILLE = {config.VILLE!r}")

    lon_min, lat_min, lon_max, lat_max = config.EMPRISE_WGS84
    emprise_ok = (-180 <= lon_min < lon_max <= 180) and (-90 <= lat_min < lat_max <= 90)
    note(emprise_ok, f"EMPRISE_WGS84 = {config.EMPRISE_WGS84} (ordre lon_min, lat_min, lon_max, lat_max)")

    note(set(config.ANNEES) <= set(config.ANNEES_AUDIT),
         f"ANNEES {config.ANNEES[0]}-{config.ANNEES[-1]} incluses dans ANNEES_AUDIT "
         f"{config.ANNEES_AUDIT[0]}-{config.ANNEES_AUDIT[-1]}")
    note(config.MOIS_ETE == [6, 7, 8], f"MOIS_ETE = {config.MOIS_ETE}")

    if config.CRS_CALCUL is None:
        info("CRS_CALCUL pas encore choisi (prévu en phase 2)")

    # Les chemins doivent être sous la racine du dépôt (chemins relatifs)
    for nom_chemin in ["DATA_BRUT", "DATA_TRAVAIL", "AUDIT", "RESULTATS", "FIGURES"]:
        chemin = getattr(config, nom_chemin)
        note(RACINE in chemin.parents, f"{nom_chemin} sous la racine du dépôt : {chemin.relative_to(RACINE)}")

# --- 4. Dossiers ---
print("\n--- Dossiers ---")
for dossier in ["00_audit", "01_acquisition", "02_pretraitement", "03_sql", "04_analyse",
                "05_resultats", "06_figures", "07_cartes", "docs", "data/brut", "data/travail"]:
    note((RACINE / dossier).is_dir(), f"dossier {dossier}")
if config is not None and not config.DATA_BRUT.exists():
    info(f"{config.DATA_BRUT.relative_to(RACINE)} n'existe pas encore (créé par les scripts d'acquisition)")

# --- 5. Fichiers d'environnement ---
print("\n--- Fichiers d'environnement ---")
for nom_fichier in ["environment.yml", "environment_lock.yml"]:
    fichier = RACINE / nom_fichier
    if not fichier.exists():
        note(False, f"{nom_fichier} absent")
        continue
    texte = fichier.read_text(encoding="utf-8", errors="replace")
    note("prefix:" not in texte, f"{nom_fichier} : pas de ligne prefix")
    note("- pip:" not in texte, f"{nom_fichier} : pas de section pip")
    if nom_fichier == "environment_lock.yml":
        note("==" not in texte, f"{nom_fichier} : aucun paquet épinglé par pip (==)")

# --- Bilan ---
n_pass = resultats.count("PASS")
n_fail = resultats.count("FAIL")
print(f"\nBilan : {n_pass} PASS, {n_fail} FAIL")
sys.exit(1 if n_fail else 0)

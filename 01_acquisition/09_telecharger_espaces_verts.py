# 09_telecharger_espaces_verts.py
# Étape 1.6 : télécharge par WFS (Bruxelles Environnement) la couche des espaces verts accessibles au public
# et celle des zones de carence, en Lambert 72, et les enregistre TELLES QUELLES.
# Vérifie que le serveur a renvoyé TOUTES les entités (un WFS peut limiter le nombre d'entités par réponse).
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 01_acquisition\09_telecharger_espaces_verts.py

import re
import sys
import json
from datetime import date
from pathlib import Path

import xml.etree.ElementTree as ET

import requests

# Le script est dans 01_acquisition/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

URL_WFS = "https://ows.environnement.brussels/green"
COUCHES = {   # nom de fichier : morceau du nom de couche cherché dans le service
    "espaces_verts_accessibles": "public_green_spaces",
    "zones_carence": "deficiency",
}
CRS = "EPSG:31370"
DOSSIER = config.DATA_BRUT / "bruxelles_environnement"
FICHIER_REQUETE = DOSSIER / "requetes_wfs.txt"

print("--- Requête ---")
print(f"Service : {URL_WFS} ; CRS : {CRS} ; date : {date.today().isoformat()}")

# --- 1. Description du service (GetCapabilities) : couches et formats, lus directement dans le XML ---
# (owslib n'arrive pas à lire la description de ce serveur en WFS 2.0 : on la lit nous-mêmes)
reponse = requests.get(URL_WFS, params={"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"}, timeout=60)
try:
    racine = ET.fromstring(reponse.content)
except ET.ParseError:
    print(f"FAIL  description du service illisible (code HTTP {reponse.status_code}). Début : {reponse.text[:300]}")
    sys.exit(1)


def nom_balise(element):
    """Nom d'une balise XML sans son espace de noms : '{http://...}Name' -> 'Name'."""
    return element.tag.split("}")[-1]


noms = []
for type_entite in racine.iter():
    if nom_balise(type_entite) == "FeatureType":
        for enfant in type_entite:
            if nom_balise(enfant) == "Name":
                noms.append(enfant.text)
print(f"INFO  {len(noms)} couches dans le service : {noms}")
if not noms:
    print("FAIL  aucune couche trouvée dans la description du service")
    sys.exit(1)

formats = set()
for element in racine.iter():
    if nom_balise(element) == "Parameter" and element.get("name") == "outputFormat":
        formats.update(v.text for v in element.iter() if nom_balise(v) == "Value")
formats = sorted(formats)
format_json = next((f for f in formats if "json" in f.lower()), None)
print(f"INFO  formats proposés : {formats}")
if format_json is None:
    print("FAIL  aucun format JSON proposé par le service : à traiter autrement (GML)")
    sys.exit(1)
print(f"PASS  format retenu : {format_json}")

# Le nom des paramètres dépend de la version du WFS réellement parlée par le serveur
VERSION = racine.get("version", "2.0.0")
if VERSION.startswith("2"):
    P_COUCHE, P_MAX = "typeNames", "count"
else:
    P_COUCHE, P_MAX = "typeName", "maxFeatures"
print(f"INFO  version WFS du serveur : {VERSION} (paramètres {P_COUCHE}, {P_MAX})")


def requete(couche, **autres):
    """Envoie une requête GetFeature avec les noms de paramètres de la bonne version."""
    parametres = {"service": "WFS", "version": VERSION, "request": "GetFeature", P_COUCHE: couche, **autres}
    return requests.get(URL_WFS, params=parametres, timeout=300)


def nombre_annonce(couche):
    """Demande au serveur combien d'entités compte la couche (resultType=hits). None si non disponible."""
    texte = requete(couche, resultType="hits").text
    trouve = re.search(r'(numberMatched|numberOfFeatures)="(\d+)"', texte)
    return int(trouve.group(2)) if trouve else None


def lire_json(reponse, couche):
    """Lit une réponse JSON ; s'arrête avec le début du message si le serveur a renvoyé une erreur."""
    try:
        return json.loads(reponse.text)
    except json.JSONDecodeError:
        print(f"FAIL  réponse non JSON pour {couche}. Début : {reponse.text[:300]}")
        sys.exit(1)


def telecharger(couche, annonce):
    """Une requête complète d'abord ; pagination seulement si le serveur a tronqué la réponse."""
    reponse = requete(couche, outputFormat=format_json, srsName=CRS)
    page = lire_json(reponse, couche)
    entites = page.get("features", [])
    if annonce is None or len(entites) >= annonce:
        return entites, reponse.url, page
    taille_page = len(entites)   # la limite réelle du serveur = ce qu'il a renvoyé la première fois
    print(f"INFO  réponse tronquée ({taille_page} sur {annonce}) : pagination par pages de {taille_page}")
    if taille_page == 0:
        print("FAIL  le serveur ne renvoie aucune entité")
        sys.exit(1)
    entites, vues, depart = [], set(), 0
    while True:
        reponse = requete(couche, outputFormat=format_json, srsName=CRS, startIndex=depart, **{P_MAX: taille_page})
        page = lire_json(reponse, couche)
        nouvelles = page.get("features", [])
        for entite in nouvelles:
            empreinte = json.dumps(entite, sort_keys=True)   # identifie une entité même sans « id »
            if empreinte in vues:
                print("FAIL  le serveur renvoie des entités déjà reçues : il ignore la pagination (startIndex)")
                sys.exit(1)
            vues.add(empreinte)
        entites.extend(nouvelles)
        if len(nouvelles) < taille_page or len(entites) >= annonce:
            return entites, reponse.url, page
        depart += taille_page


# --- 2. Téléchargement de chaque couche ---
DOSSIER.mkdir(parents=True, exist_ok=True)
lignes_requete = [f"Date de téléchargement : {date.today().isoformat()}", f"Service : {URL_WFS}"]
for fichier, morceau in COUCHES.items():
    print(f"\n--- {fichier} ---")
    candidates = [n for n in noms if morceau in n.lower()]
    # On préfère le nom qui se termine exactement par le morceau cherché (pas une archive datée)
    exactes = [n for n in candidates if n.lower().endswith(morceau)]
    couche = (exactes or candidates or [None])[0]
    if couche is None:
        print(f"FAIL  aucune couche contenant « {morceau} »")
        sys.exit(1)
    print(f"PASS  couche retenue : {couche} (candidates : {candidates})")

    annonce = nombre_annonce(couche)
    entites, url, derniere_page = telecharger(couche, annonce)
    if annonce is None:
        print(f"INFO  nombre total non annoncé par le serveur ; {len(entites)} entités reçues")
    elif len(entites) == annonce:
        print(f"PASS  {len(entites)} entités reçues = {annonce} annoncées")
    else:
        print(f"FAIL  {len(entites)} entités reçues pour {annonce} annoncées")
        sys.exit(1)

    collection = {"type": "FeatureCollection", "features": entites}
    if "crs" in derniere_page:            # on garde la déclaration de CRS renvoyée par le serveur
        collection["crs"] = derniere_page["crs"]
    chemin = DOSSIER / f"{fichier}.geojson"
    chemin.write_text(json.dumps(collection), encoding="utf-8")
    print(f"Fichier écrit : {chemin.relative_to(RACINE)} ({chemin.stat().st_size / 1e6:.1f} Mo)")
    lignes_requete.append(f"{fichier} : couche {couche}, {len(entites)} entités, dernière URL : {url}")

FICHIER_REQUETE.write_text("\n".join(lignes_requete) + "\n", encoding="utf-8")
print(f"\nRequêtes notées : {FICHIER_REQUETE.relative_to(RACINE)}")
print("Étape suivante : python 00_audit\\10_verif_espaces_verts.py")

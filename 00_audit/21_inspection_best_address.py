# 21_inspection_best_address.py — inspection en LECTURE SEULE du registre d'adresses bruxellois (BeSt Address)
# (phase 2, étape 2.4). But : avant tout téléchargement, savoir quelles couches le service propose,
# quels attributs elles ont, combien d'adresses elles contiennent et SI les numéros de boîte sont remplis.
# Ne télécharge que quelques exemples (5 adresses) ; n'écrit rien.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\21_inspection_best_address.py > data\travail\bruxelles\audit\21_sortie.txt

import re
import sys
import json

import requests

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

URL_WFS = "https://geoservices-urbis.irisnet.be/geoserver/urbisvector/wfs"   # WFS UrbIS (le service « com » de la fiche BeSt répond 404)
DELAI = 120


def info(message):
    print(f"INFO  {message}")


def requete(params):
    """GET sur le WFS ; renvoie le texte de la réponse (ou quitte avec le message d'erreur)."""
    base = {"service": "WFS", "version": "2.0.0"}
    try:
        r = requests.get(URL_WFS, params={**base, **params}, timeout=DELAI)
    except requests.RequestException as erreur:
        sys.exit(f"FAIL  service injoignable : {erreur}")
    if r.status_code != 200:
        sys.exit(f"FAIL  HTTP {r.status_code} pour {r.url}")
    return r.text, r.url


def compter(couche, filtre=None):
    """Nombre d'objets (resultType=hits), éventuellement avec un filtre CQL (extension GeoServer)."""
    params = {"request": "GetFeature", "typeNames": couche, "resultType": "hits"}
    if filtre:
        params["CQL_FILTER"] = filtre
    texte, _ = requete(params)
    trouve = re.search(r'numberMatched="(\d+)"', texte)
    return int(trouve.group(1)) if trouve else None


# --- 1. Couches du service ---
print("--- 1. Couches du service ---")
texte, url = requete({"request": "GetCapabilities"})
noms = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", texte)
titres = re.findall(r"<(?:wfs:)?Title>([^<]+)</(?:wfs:)?Title>", texte)
info(f"{len(noms)} couche(s)")
for nom in noms:
    print(f"        {nom}")
couches = [n for n in noms if "address" in n.lower() or "adres" in n.lower()]
if not couches:
    sys.exit("FAIL  aucune couche d'adresses trouvée : colle-moi cette sortie")

# --- 2. Pour chaque couche d'adresses (Addresses, AddressNumbers) : attributs, nombre, exemples, boîtes ---
for couche in couches:
    print(f"\n--- 2. Couche {couche} ---")
    schema, _ = requete({"request": "DescribeFeatureType", "typeNames": couche})
    attributs = re.findall(r'<xsd:element[^>]*name="([^"]+)"[^>]*type="([^"]+)"', schema)
    info("attributs : " + ", ".join(f"{n} ({t.split(':')[-1]})" for n, t in attributs))

    n_total = compter(couche)
    info(f"nombre d'objets : {n_total}")

    exemples, url = requete({"request": "GetFeature", "typeNames": couche, "count": 5,
                             "outputFormat": "application/json", "srsName": "EPSG:31370"})
    try:
        donnees = json.loads(exemples)
        print("[5 exemples : propriétés]")
        for f in donnees.get("features", []):
            print("        " + json.dumps(f.get("properties", {}), ensure_ascii=False)[:400])
        if donnees.get("features"):
            info(f"géométrie du 1er exemple : {json.dumps(donnees['features'][0].get('geometry'))[:200]}")
    except json.JSONDecodeError:
        info(f"exemples non lisibles en GeoJSON ; début de la réponse : {exemples[:300]}")

    # Numéros de boîte : l'attribut existe-t-il, et combien d'adresses en ont un ?
    boites = [n for n, _ in attributs if "box" in n.lower() or "bus" in n.lower() or "boite" in n.lower()]
    if not boites:
        info("aucun attribut de numéro de boîte dans cette couche")
    for b in boites:
        n_boite = compter(couche, f"{b} IS NOT NULL AND {b} <> ''")
        if n_boite is None or not n_total:
            info(f"comptage des boîtes impossible pour « {b} » (filtre refusé par le serveur)")
        else:
            info(f"adresses avec « {b} » rempli : {n_boite} sur {n_total} ({n_boite / n_total:.1%})")

    # Statut : combien d'adresses « current » ?
    statuts = [n for n, _ in attributs if "status" in n.lower()]
    for s in statuts:
        for valeur in ("current", "Current"):
            n_s = compter(couche, f"{s} = '{valeur}'")
            if n_s:
                info(f"adresses avec {s} = '{valeur}' : {n_s}")

print("\nFin de l'inspection (rien n'est écrit).")

# 19_verif_reseau_pieton.py — contrôle en LECTURE SEULE de la règle piétonne définitive (phase 2, étape 2.3)
# La règle est dans outils_reseau.py ; les seuils des entrées dans config.py (SEUIL_ENTREE_DIFFUSE_M, ENTREE_PENETRATION_M).
# Ne crée, ne modifie et n'écrit rien. Aucun croisement avec la chaleur ou la population.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\19_verif_reseau_pieton.py > data\travail\bruxelles\audit\19_sortie.txt

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py et les modules partagés
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config
from outils_ev import charger_ev, masque_filtre_principal
from outils_reseau import lire_voies_osm, ajouter_blocs, compter_entrees

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

FICHIER_OSM = config.DATA_BRUT / "reseau" / "osm_highway_20261101.json"
MIN_CONNEXITE = 0.95                      # critère de l'audit 12
MIN_SURFACE_AVEC_ENTREE = 0.99            # garde-fou : part de la surface du filtre principal joignable
PARCS = {"Bois de la Cambre": 27, "Laeken": 14, "Soignes": 105}   # km de chemins à l'audit 12 (repère)

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 40)
resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    print(f"INFO  {message}")


def km(serie):
    return round(serie.sum() / 1000, 1)


# --- 1. Cascade avec la règle définitive ---
print("--- 1. Cascade du filtre piéton (règle définitive) ---")
seuil = getattr(config, "SEUIL_ENTREE_DIFFUSE_M", None)
penetration = getattr(config, "ENTREE_PENETRATION_M", None)
if seuil is None or penetration is None:
    sys.exit("FAIL  SEUIL_ENTREE_DIFFUSE_M ou ENTREE_PENETRATION_M absent de config.py : complète le bloc « Réseau piéton »")
osm, n_lues = lire_voies_osm(FICHIER_OSM, config.CRS_CALCUL)
info(f"{n_lues} voies lues, {len(osm)} complètes, {km(osm['longueur'])} km")
cascade = osm.groupby(osm["raison"].fillna("00 gardée"))["longueur"].agg(voies="size", km="sum")
cascade["km"] = (cascade["km"] / 1000).round(1)
print(cascade.to_string())

trunk_garde = osm[osm["highway"].isin(["trunk", "trunk_link"]) & osm["raison"].isna()]
info(f"trunk gardés grâce à un trottoir noté (ou foot autorisé) : {len(trunk_garde)} voies, {km(trunk_garde['longueur'])} km")
print(trunk_garde.groupby("name", dropna=False)["longueur"].sum().div(1000).round(2)
      .sort_values(ascending=False).head(10).to_string())

# --- 2. Diagnostic « access interdit » ---
print("\n--- 2. Diagnostic : voies exclues par access ---")
acces = osm[osm["raison"] == "07 access interdit"]
print(acces.pivot_table(index="highway", columns="access", values="longueur", aggfunc="sum", fill_value=0)
      .div(1000).round(1).assign(total=lambda d: d.sum(axis=1)).sort_values("total", ascending=False).head(12).to_string())

ev_tout = charger_ev(config)
ev = ev_tout[masque_filtre_principal(ev_tout, config)].copy()
morceaux = gpd.overlay(acces[["osm_id", "highway", "access", "foot", "name", "geometry"]],
                       ev[["name_f", "subtype_f", "geometry"]], how="intersection", keep_geom_type=True)
morceaux["m_dans_ev"] = morceaux.length
info(f"exclus par access À L'INTÉRIEUR des espaces verts du filtre principal : {km(morceaux['m_dans_ev'])} km")
print("[par type de voie et sous-type d'espace vert (km)]")
print(morceaux.pivot_table(index="highway", columns="subtype_f", values="m_dans_ev", aggfunc="sum", fill_value=0)
      .div(1000).round(2).to_string())
print("[les 15 plus longs morceaux, à vérifier à l'œil]")
print(morceaux.sort_values("m_dans_ev", ascending=False)
      [["osm_id", "highway", "access", "foot", "name", "name_f", "m_dans_ev"]].head(15).round(0).to_string(index=False))

# --- 3. Connexité finale ---
print("\n--- 3. Connexité ---")
garde = osm[osm["raison"].isna()].copy()
principal = ajouter_blocs(garde)
part = garde.loc[garde["bloc"] == principal, "longueur"].sum() / garde["longueur"].sum()
note(part >= MIN_CONNEXITE, f"plus grand bloc : {part:.2%} de la longueur gardée (min {MIN_CONNEXITE:.0%})")
reseau = garde[garde["bloc"] == principal].reset_index(drop=True)
info(f"réseau piéton final : {len(reseau)} voies, {km(reseau['longueur'])} km ; "
     f"écartés hors du grand bloc : {garde['bloc'].nunique() - 1} blocs, {km(garde.loc[garde['bloc'] != principal, 'longueur'])} km")

for nom, repere in PARCS.items():
    poly = ev_tout[ev_tout["name_f"].astype(str).str.contains(nom, case=False, regex=False)].geometry.union_all()
    longueur = reseau.intersection(poly).length.sum() / 1000 if poly is not None else 0
    note(longueur > 0, f"chemins dans « {nom} » : {longueur:.1f} km (audit 12, réseau provisoire : {repere} km)")

# --- 4. Entrées ---
print(f"\n--- 4. Entrées (ponctuelles : contour extérieur, chemin relié atteignant {penetration} m à l'intérieur ; diffuses à moins de {seuil} m) ---")
fermes = getattr(config, "EV_FERMES_PGS_ID", [])
info(f"espaces vérifiés fermés (config.EV_FERMES_PGS_ID) : {fermes}")
ev = compter_entrees(ev, reseau, seuil, penetration, fermes)
bilan = ev.groupby("type_entree")["ha"].agg(espaces="size", ha="sum").round(1)
print(bilan.to_string())
part_surface = ev.loc[ev["type_entree"] != "injoignable", "ha"].sum() / ev["ha"].sum()
note(part_surface >= MIN_SURFACE_AVEC_ENTREE,
     f"surface du filtre principal avec au moins une entrée : {part_surface:.2%} (min {MIN_SURFACE_AVEC_ENTREE:.0%})")
injoignables = ev[ev["type_entree"] == "injoignable"]
if len(injoignables):
    print("[espaces injoignables (limites)]")
    print(injoignables[["pgs_id", "name_f", "subtype_f", "ha", "distance_reseau_m"]].round(1).to_string(index=False))

print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")

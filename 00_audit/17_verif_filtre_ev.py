# 17_verif_filtre_ev.py — contrôle en LECTURE SEULE du filtre principal des espaces verts
# (phase 2, étape 2.2). Le filtre est lu dans config.py (EV_STATUT, EV_PCT_VEG_MIN, EV_EAU_COMPTEE, EV_SOUS_TYPES)
# et appliqué en mémoire. Ne crée, ne modifie et n'écrit rien.
# Aucun croisement avec la chaleur ou la population : contrôle de qualité seulement.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\17_verif_filtre_ev.py > data\travail\bruxelles\audit\17_sortie.txt

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely import make_valid

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

sys.stdout.reconfigure(encoding="utf-8")   # sortie en UTF-8, même redirigée vers un fichier sous Windows

FICHIER = config.DATA_BRUT / "bruxelles_environnement" / "espaces_verts_accessibles.geojson"
SEUIL_GRAND_HA = 5                      # grands espaces exclus listés pour vérification à l'œil
COLONNES = ["name_f", "subtype_f", "status_foncier", "pct_veg", "pct_water", "ha"]

pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 45)

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def info(message):
    print(f"INFO  {message}")


# --- 1. Filtre lu dans config.py ---
print("--- 1. Filtre (config.py) ---")
try:
    statuts, veg_min, sous_types = config.EV_STATUT, config.EV_PCT_VEG_MIN, config.EV_SOUS_TYPES
    eau_comptee = config.EV_EAU_COMPTEE
except AttributeError as erreur:
    sys.exit(f"FAIL  filtre absent de config.py ({erreur}) : ajoute le bloc « Espaces verts »")
mesure = "pct_veg + pct_water" if eau_comptee else "pct_veg"
info(f"status_foncier ∈ {statuts} ET {mesure} > {veg_min} ET subtype_f ∈ {sous_types}")

ev = gpd.read_file(FICHIER)
ev["geometry"] = ev.geometry.apply(make_valid)      # en mémoire seulement
ev["ha"] = ev.geometry.area / 1e4

# Chaque valeur du filtre doit exister dans la couche (attrape une faute de frappe ou d'accent)
for valeur in statuts:
    note(valeur in set(ev["status_foncier"]), f"status_foncier « {valeur} » présent dans la couche")
for valeur in sous_types:
    note(valeur in set(ev["subtype_f"]), f"subtype_f « {valeur} » présent dans la couche")

ok_statut = ev["status_foncier"].isin(statuts)
# Couverture : végétation seule, ou végétation + eau (règle IBSA, Focus n° 63). NaN -> False : exclu
ev["couverture"] = ev["pct_veg"] + ev["pct_water"].fillna(0) if eau_comptee else ev["pct_veg"]
ok_veg = ev["couverture"] > veg_min
ok_type = ev["subtype_f"].isin(sous_types)
ev["garde"] = ok_statut & ok_veg & ok_type

# --- 2. Effet de chaque règle, appliquées l'une après l'autre ---
print("\n--- 2. Cascade du filtre ---")
etapes = [("couche entière", pd.Series(True, index=ev.index)),
          ("+ statut", ok_statut),
          ("+ végétation", ok_statut & ok_veg),
          ("+ sous-type", ev["garde"])]
cascade = pd.DataFrame([{"étape": nom, "espaces": int(m.sum()), "ha": round(ev.loc[m, "ha"].sum(), 1)}
                        for nom, m in etapes])
print(cascade.to_string(index=False))
info(f"exclus pour pct_veg manquant : {int(ev['pct_veg'].isna().sum())}")

garde = ev[ev["garde"]]
note(len(garde) > 0, f"filtre principal : {len(garde)} espaces, {garde['ha'].sum():.1f} ha")

# --- 3. Ce qui est gardé ---
print("\n--- 3. Espaces gardés ---")
par_type = garde.groupby("subtype_f")["ha"].agg(espaces="size", ha="sum").round(1)
print(par_type.to_string())
grands = garde["ha"] >= 1
info(f"< 1 ha (seuil 200 m) : {(~grands).sum()} espaces, {garde.loc[~grands, 'ha'].sum():.1f} ha ; "
     f">= 1 ha (seuil 400 m) : {grands.sum()} espaces, {garde.loc[grands, 'ha'].sum():.1f} ha")

soignes = ev[ev["name_f"].astype(str).str.lower().str.contains("soignes")]
note(len(soignes) > 0 and soignes["garde"].all(),
     f"forêt de Soignes gardée ({len(soignes)} objet(s), {soignes['ha'].sum():.0f} ha)")

# --- 4. Grands espaces exclus : vérification à l'œil ---
print(f"\n--- 4. Espaces exclus de {SEUIL_GRAND_HA} ha ou plus ---")
exclus = ev[~ev["garde"]].copy()


def raisons(ligne):
    r = []
    if ligne["status_foncier"] not in statuts:
        r.append("statut")
    if not ligne["couverture"] > veg_min:
        r.append("végétation")
    if ligne["subtype_f"] not in sous_types:
        r.append("sous-type")
    return ", ".join(r)


exclus["raison"] = exclus.apply(raisons, axis=1)
grands_exclus = exclus[exclus["ha"] >= SEUIL_GRAND_HA].sort_values("ha", ascending=False)
print(grands_exclus[COLONNES + ["raison"]].round(1).to_string())

parcs_exclus = exclus[exclus["name_f"].astype(str).str.lower().str.startswith("parc") & (exclus["ha"] >= 1)]
print(f"\n[espaces nommés « Parc… » de 1 ha ou plus exclus : {len(parcs_exclus)}]")
if len(parcs_exclus):
    print(parcs_exclus.sort_values("ha", ascending=False)[COLONNES + ["raison"]].round(1).to_string())

# --- 5. Eau : espaces qui ne passent le seuil que grâce à l'eau ---
print("\n--- 5. Test de l'eau ---")
eau = ev[ok_statut & ok_type & (ev["pct_veg"] <= veg_min) & ((ev["pct_veg"] + ev["pct_water"]) > veg_min)]
info(f"pct_veg <= {veg_min} mais pct_veg + pct_water > {veg_min} : {len(eau)} espaces, {eau['ha'].sum():.1f} ha "
     f"({'gardés : eau comptée' if eau_comptee else 'exclus : eau non comptée'})")
if len(eau):
    print(eau.sort_values("ha", ascending=False)[COLONNES].round(1).head(15).to_string())

# --- 6. Variante README : seuil de végétation à 40 % et 60 % ---
print("\n--- 6. Variante README (seuil de végétation) ---")
for seuil in (40, veg_min, 60):
    m = ok_statut & ok_type & (ev["couverture"] > seuil)
    info(f"{mesure} > {seuil} : {int(m.sum())} espaces, {ev.loc[m, 'ha'].sum():.1f} ha")

print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")

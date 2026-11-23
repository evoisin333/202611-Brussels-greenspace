# 16_audit_attributs_ev.py — contrôle en LECTURE SEULE des attributs des espaces verts accessibles
# (Bruxelles Environnement, couche 2024) — phase 2, étape 2.2.
# But : savoir ce que la couche permet de filtrer AVANT de fixer le filtre principal.
# Ne crée, ne modifie et n'écrit rien : uniquement des impressions à l'écran.
# Aucun croisement avec la chaleur ou la population : contrôle de qualité seulement.
#
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\16_audit_attributs_ev.py

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely import make_valid

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

FICHIER = config.DATA_BRUT / "bruxelles_environnement" / "espaces_verts_accessibles.geojson"
MAX_CATEGORIES = 30               # une colonne texte avec ≤ 30 valeurs est traitée comme une catégorie
TOLERANCE_FUSION_M = 5            # 2e test de fusion : polygones séparés de moins de 5 m
CAS_CONNUS = ["scheut", "marais de jette", "moeras van jette"]

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 40)


def info(message):
    print(f"INFO  {message}")


def classe_taille(ha):
    """Classe de taille utilisée par BE (seuil 1 ha) et par l'IBSA (seuil 0,05 ha)."""
    if ha < 0.05:
        return "a) < 0,05 ha"
    if ha < 1:
        return "b) 0,05-1 ha"
    return "c) >= 1 ha"


# --- 1. Colonnes ---
print("--- 1. Colonnes ---")
ev = gpd.read_file(FICHIER)
ev["geometry"] = ev.geometry.apply(make_valid)        # en mémoire seulement
ev["ha_calc"] = ev.geometry.area / 1e4                # surface recalculée depuis la géométrie
info(f"{len(ev)} espaces, {ev['ha_calc'].sum():.0f} ha au total (audit 10 : 3 466 ha)")
resume = pd.DataFrame({
    "type": ev.dtypes.astype(str),
    "manquants": ev.isna().sum(),
    "valeurs_distinctes": ev.nunique(dropna=True),
    "exemple": ev.iloc[0],
}).drop(index=["geometry", "ha_calc"])
print(resume.to_string())

# --- 2. Attributs à catégories (on y cherche propriétaire, gestionnaire, statut) ---
print("\n--- 2. Attributs à catégories (nombre d'objets et surface recalculée) ---")
colonnes_texte = [c for c in ev.columns
                  if c not in ("geometry", "ha_calc") and not pd.api.types.is_numeric_dtype(ev[c])
                  and 1 < ev[c].nunique() <= MAX_CATEGORIES]
for col in colonnes_texte:
    tableau = ev.groupby(col, dropna=False)["ha_calc"].agg(objets="size", ha="sum").sort_values("ha", ascending=False)
    tableau["ha"] = tableau["ha"].round(1)
    print(f"\n[{col}]")
    print(tableau.to_string())

# --- 3. Cas connus (Scheutbos, Marais de Jette) ---
print("\n--- 3. Cas connus ---")
colonnes_nom = [c for c in ev.columns if any(m in c.lower() for m in ("name", "nom", "naam"))]
if not colonnes_nom:
    info("aucune colonne de nom trouvée")
for col in colonnes_nom:
    texte = ev[col].astype(str).str.lower()
    for cas in CAS_CONNUS:
        trouves = ev[texte.str.contains(cas, regex=False)]
        if len(trouves):
            print(f"\n[{col} contient « {cas} »]")
            print(trouves.drop(columns="geometry").to_string())
        else:
            info(f"[{col}] aucun espace contenant « {cas} »")

# --- 4. Couverture végétale ---
print("\n--- 4. Couverture végétale ---")
candidats = [c for c in ev.columns if c.lower() == "pct_veg"] or \
            [c for c in ev.columns if "veg" in c.lower() and pd.api.types.is_numeric_dtype(ev[c])]
if not candidats:
    sys.exit("FAIL  aucune colonne de couverture végétale trouvée : colle-moi la section 1")
col_veg = candidats[0]
veg = ev[col_veg]
echelle = 1 if veg.max() <= 1 else 100                # fraction (0-1) ou pourcentage (0-100)
seuil = 0.5 * echelle
info(f"colonne utilisée : {col_veg} ; échelle 0-{echelle} ; seuil BE « plus de 50 % » = {col_veg} > {seuil:g}")
print(veg.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(3).to_string())
autour = ev[(veg >= 0.4 * echelle) & (veg <= 0.6 * echelle)]
info(f"autour du seuil (40-60 %) : {len(autour)} espaces, {autour['ha_calc'].sum():.1f} ha")
pile = ev[veg == seuil]
info(f"exactement 50 % : {len(pile)} espaces, {pile['ha_calc'].sum():.1f} ha (exclus par « plus de 50 % »)")
info(f"manquants dans {col_veg} : {veg.isna().sum()}")

ev["veg_sup_50"] = veg > seuil

# Sous-type × végétation > 50 %
col_type = "subtype_f" if "subtype_f" in ev.columns else None
if col_type:
    print(f"\n[{col_type} × {col_veg} > 50 %]")
    tableau = ev.pivot_table(index=col_type, columns="veg_sup_50", values="ha_calc",
                             aggfunc=["size", "sum"], fill_value=0)
    tableau.columns = [f"{'objets' if a == 'size' else 'ha'}_{'oui' if b else 'non'}" for a, b in tableau.columns]
    tableau["mediane_veg"] = ev.groupby(col_type)[col_veg].median()
    print(tableau.round(1).to_string())

    # L'eau est-elle comptée ? Les étangs sous le seuil le diront
    etangs = ev[ev[col_type].astype(str).str.lower().str.contains("tang|berge", regex=True) & ~ev["veg_sup_50"]]
    print(f"\n[étangs et berges sous le seuil : {len(etangs)} espaces, {etangs['ha_calc'].sum():.1f} ha]")
    colonnes = [c for c in colonnes_nom + [col_veg, "ha_calc"] if c in ev.columns]
    if len(etangs):
        print(etangs[colonnes].sort_values("ha_calc", ascending=False).head(15).round(2).to_string())
else:
    info("colonne subtype_f absente : tableau par sous-type non calculé")

# --- 5. Tailles : polygone par polygone, puis après fusion des polygones voisins ---
print("\n--- 5. Classes de taille et effet de la fusion des polygones voisins ---")


def effet_fusion(sel, tolerance, nom):
    """Fusionne en mémoire les polygones qui se touchent (ou à moins de `tolerance` m),
    puis compte les espaces qui changent de classe de taille."""
    if len(sel) == 0:
        return
    zones = sel.geometry.buffer(tolerance / 2) if tolerance else sel.geometry
    groupes = gpd.GeoDataFrame(geometry=[zones.union_all()], crs=sel.crs).explode(index_parts=False)
    groupes["groupe"] = range(len(groupes))
    points = gpd.GeoDataFrame(geometry=sel.geometry.representative_point(), crs=sel.crs)
    lien = gpd.sjoin(points, groupes, predicate="within", how="left")["groupe"]
    lien = lien[~lien.index.duplicated()]
    s = sel.assign(groupe=lien)
    s["ha_groupe"] = s.groupby("groupe")["ha_calc"].transform("sum")   # surface réelle, sans le tampon
    s["classe_avant"] = s["ha_calc"].apply(classe_taille)
    s["classe_apres"] = s["ha_groupe"].apply(classe_taille)
    change = s[s["classe_avant"] != s["classe_apres"]]
    print(f"\n[{nom} — fusion {'des polygones qui se touchent' if not tolerance else f'à moins de {tolerance} m'}]")
    print(f"  {len(sel)} polygones -> {s['groupe'].nunique()} groupes")
    print(f"  changent de classe : {len(change)} polygones, {change['ha_calc'].sum():.1f} ha "
          f"({change['ha_calc'].sum() / sel['ha_calc'].sum():.1%} de la surface)")
    print(f"  dont passent de < 1 ha à >= 1 ha : "
          f"{((change['classe_avant'] != 'c) >= 1 ha') & (change['classe_apres'] == 'c) >= 1 ha')).sum()} polygones")


for nom, sel in [("couche entière", ev), (f"{col_veg} > 50 %", ev[ev["veg_sup_50"]])]:
    tailles = sel.groupby(sel["ha_calc"].apply(classe_taille))["ha_calc"].agg(objets="size", ha="sum").round(1)
    print(f"\n[{nom} — polygone par polygone]")
    print(tailles.to_string())
    effet_fusion(sel, 0, nom)
    effet_fusion(sel, TOLERANCE_FUSION_M, nom)

print("\nFin du contrôle (lecture seule, aucun fichier écrit).")

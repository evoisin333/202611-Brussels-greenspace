# 10_verif_espaces_verts.py
# Contrôle en LECTURE SEULE des couches de Bruxelles Environnement téléchargées par
# 01_acquisition/09_telecharger_espaces_verts.py (espaces verts accessibles au public, zones de carence).
# Critères fixés avant les données (journal, 20/11/2026). Aucun fichier écrit.
# Lancement (Miniforge Prompt, environnement chaleur, depuis la racine du dépôt) :
#   python 00_audit\10_verif_espaces_verts.py

import sys
from pathlib import Path

import numpy as np
import geopandas as gpd

# Le script est dans 00_audit/ : on ajoute la racine du dépôt pour lire config.py
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
import config

DOSSIER = config.DATA_BRUT / "bruxelles_environnement"
FICHIER_EV = DOSSIER / "espaces_verts_accessibles.geojson"
FICHIER_CARENCE = DOSSIER / "zones_carence.geojson"
FICHIER_REGION = config.DATA_BRUT / "urbis_region.geojson"

SURFACE_REF_HA = 3194          # Bruxelles Environnement, données 2023 (la couche est en version 2024)
TOLERANCE_SURFACE = 0.05       # ±5 %
X_MIN, X_MAX = 130_000, 170_000   # plage plausible de Bruxelles en Lambert 72 (m)
Y_MIN, Y_MAX = 155_000, 185_000
ATTRIBUTS = ["pgs_id", "pct_veg", "subtype_f", "status_foncier", "area_m2"]
MAX_VIDES = 0.05               # ≤ 5 % de valeurs vides par attribut utile
MAX_INVALIDES = 0.01           # ≤ 1 % de polygones invalides

resultats = []


def note(ok, message):
    """Enregistre et affiche un contrôle PASS ou FAIL."""
    statut = "PASS" if ok else "FAIL"
    resultats.append(statut)
    print(f"{statut}  {message}")


def controle_crs_axes(couche, nom):
    """CRS lu + coordonnées dans la plage de Bruxelles en Lambert 72 (détecte un CRS mal déclaré ou des axes inversés)."""
    epsg = couche.crs.to_epsg() if couche.crs is not None else None
    xmin, ymin, xmax, ymax = couche.total_bounds
    note(epsg == 31370, f"{nom} : CRS EPSG:{epsg} (attendu 31370)")
    note(X_MIN <= xmin and xmax <= X_MAX and Y_MIN <= ymin and ymax <= Y_MAX,
         f"{nom} : coordonnées dans la plage de Bruxelles (x {xmin:,.0f}-{xmax:,.0f}, y {ymin:,.0f}-{ymax:,.0f})")


region = gpd.read_file(FICHIER_REGION).to_crs(31370).geometry.union_all()

# --- 1. Espaces verts accessibles au public ---
print("--- Espaces verts accessibles au public ---")
ev = gpd.read_file(FICHIER_EV)
print(f"INFO  {len(ev)} entités ; colonnes : {[c for c in ev.columns if c != 'geometry']}")
controle_crs_axes(ev, "espaces verts")
if ev.crs is None or ev.crs.to_epsg() != 31370:
    ev = ev.set_crs(31370, allow_override=True)   # pour continuer les contrôles si seul le CRS déclaré manque

types = ev.geom_type.value_counts()
print(f"INFO  types de géométrie : {types.to_dict()}")
polygones = ev[ev.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
lignes = ev[ev.geom_type.isin(["LineString", "MultiLineString"])]
print(f"INFO  {len(polygones)} polygones, {len(lignes)} lignes (chemins : {lignes.length.sum() / 1000:.1f} km)")

manquants = [a for a in ATTRIBUTS if a not in ev.columns]
note(not manquants, "attributs utiles présents" + (f" (manquants : {manquants})" if manquants else ""))
for attribut in [a for a in ATTRIBUTS if a in ev.columns]:
    part_vide = ev[attribut].isna().mean()
    note(part_vide <= MAX_VIDES, f"{attribut} : {100 * part_vide:.1f} % de valeurs vides (max 5 %)")
if "pgs_id" in ev.columns:
    note(not ev["pgs_id"].dropna().duplicated().any(), "aucun pgs_id en double")

part_invalides = (~polygones.is_valid).mean() if len(polygones) else 1
note(part_invalides <= MAX_INVALIDES, f"polygones invalides : {100 * part_invalides:.2f} % (max 1 %, réparés au prétraitement)")

polygones["surface_calc"] = polygones.area
if "area_m2" in polygones.columns:
    # Malgré son nom, area_m2 peut être en hectares : on mesure le rapport surface calculée / surface déclarée
    rapport = (polygones["surface_calc"] / polygones["area_m2"]).median()
    unite = "m²" if abs(rapport - 1) <= 0.01 else ("ha" if abs(rapport - 10_000) / 10_000 <= 0.01 else "inconnue")
    note(unite != "inconnue", f"area_m2 cohérente avec la surface calculée : rapport médian {rapport:,.4f} "
                              f"→ unité réelle de area_m2 : {unite} (1 = m², 10 000 = ha, à 1 % près)")

surface_ha = polygones["surface_calc"].sum() / 1e4
note(abs(surface_ha - SURFACE_REF_HA) / SURFACE_REF_HA <= TOLERANCE_SURFACE,
     f"surface totale des polygones : {surface_ha:,.0f} ha (référence {SURFACE_REF_HA:,} ha, données 2023, ±5 %)")
union = polygones.geometry.union_all()
print(f"INFO  chevauchements entre polygones : {surface_ha - union.area / 1e4:.1f} ha comptés deux fois")
part_region = union.intersection(region).area / union.area
note(part_region >= 0.99, f"part de la surface dans la Région : {100 * part_region:.2f} % (min 99 %)")

print("\nINFO  surface par sous-type (ha, % du total) :")
if "subtype_f" in polygones.columns:
    par_type = polygones.groupby("subtype_f", dropna=False)["surface_calc"].sum() / 1e4
    for sous_type, ha in par_type.sort_values(ascending=False).items():
        print(f"        {str(sous_type):<28} {ha:8.1f} ha  {100 * ha / surface_ha:5.1f} %")
for seuil in [0.5, 1]:
    print(f"INFO  polygones d'au moins {seuil} ha : {(polygones['surface_calc'] >= seuil * 1e4).sum()}")
if "name_f" in polygones.columns:
    soignes = polygones[polygones["name_f"].astype(str).str.contains("Soignes", case=False)]
    print(f"INFO  polygones nommés « Soignes » : {len(soignes)}, {soignes['surface_calc'].sum() / 1e4:.0f} ha")
if "pct_veg" in polygones.columns:
    veg = polygones["pct_veg"].dropna()
    print(f"INFO  pct_veg : min {veg.min()}, médiane {veg.median()}, max {veg.max()} (vérifier l'échelle : 0-100 ou 0-1)")
    seuil_50 = 50 if veg.max() > 1 else 0.5
    print(f"INFO  surface avec pct_veg > 50 % : {polygones.loc[polygones['pct_veg'] > seuil_50, 'surface_calc'].sum() / 1e4:,.0f} ha")
if "status_foncier" in polygones.columns:
    print(f"INFO  statut foncier (nombre) : {polygones['status_foncier'].value_counts(dropna=False).to_dict()}")

# --- 2. Zones de carence ---
print("\n--- Zones de carence ---")
carence = gpd.read_file(FICHIER_CARENCE)
print(f"INFO  {len(carence)} entités ; colonnes : {[c for c in carence.columns if c != 'geometry']}")
controle_crs_axes(carence, "zones de carence")
if carence.crs is None or carence.crs.to_epsg() != 31370:
    carence = carence.set_crs(31370, allow_override=True)
print(f"INFO  types de géométrie : {carence.geom_type.value_counts().to_dict()}")
part_inv_carence = (~carence.is_valid).mean() if len(carence) else 1
note(part_inv_carence <= MAX_INVALIDES, f"zones de carence invalides : {100 * part_inv_carence:.2f} % (max 1 %)")
surface_carence = carence.geometry.union_all().intersection(region).area / 1e6
print(f"INFO  surface des zones de carence dans la Région : {surface_carence:.1f} km² ({100 * surface_carence / (region.area / 1e6):.1f} % de la Région)")

# --- Bilan ---
print(f"\nBilan : {resultats.count('PASS')} PASS, {resultats.count('FAIL')} FAIL")
sys.exit(1 if "FAIL" in resultats else 0)

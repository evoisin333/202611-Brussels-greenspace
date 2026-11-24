# outils_ev.py — fonctions partagées pour les espaces verts (module sans numéro, importé par les scripts)
# Le filtre principal est défini UNE fois ici, à partir des paramètres de config.py,
# pour que tous les scripts (contrôles, chargement, analyse) utilisent exactement la même règle.

import geopandas as gpd
from shapely import make_valid


def charger_ev(config):
    """Lit la couche brute des espaces verts accessibles, corrige les géométries EN MÉMOIRE
    et ajoute la surface recalculée en hectares (colonne ha)."""
    fichier = config.DATA_BRUT / "bruxelles_environnement" / "espaces_verts_accessibles.geojson"
    ev = gpd.read_file(fichier)
    ev["geometry"] = ev.geometry.apply(make_valid)
    ev["ha"] = ev.geometry.area / 1e4
    return ev


def couverture(ev, config):
    """Couverture utilisée pour le seuil : végétation seule, ou végétation + eau (règle IBSA)."""
    if config.EV_EAU_COMPTEE:
        return ev["pct_veg"] + ev["pct_water"].fillna(0)
    return ev["pct_veg"]


def masque_filtre_principal(ev, config):
    """True pour les espaces du filtre principal (étape 2.2) ; NaN -> exclu."""
    return (ev["status_foncier"].isin(config.EV_STATUT)
            & (couverture(ev, config) > config.EV_PCT_VEG_MIN)
            & ev["subtype_f"].isin(config.EV_SOUS_TYPES))

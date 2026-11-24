# outils_reseau.py — fonctions partagées pour le réseau piéton (module sans numéro, importé par les scripts)
# La règle piétonne est définie UNE fois ici (étape 2.3), pour que contrôles, chargement et analyse
# utilisent exactement la même. Hiérarchie OSM : foot > access > défaut belge du type de voie.

import json

import numpy as np
import shapely
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

NON_CONSTRUIT = {"construction", "proposed", "planned", "abandoned", "razed", "disused"}
TYPE_EXCLU = {"raceway", "bus_guideway", "busway", "platform", "rest_area", "services", "escape", "no"}
AUTOROUTE = {"motorway", "motorway_link"}           # foot=no par défaut en Belgique
TRUNK = {"trunk", "trunk_link"}                     # foot=no par défaut, sauf trottoir noté sur la voie
CHEMIN_PIETON = {"footway", "path", "pedestrian", "steps"}
INTERIEUR = {"corridor", "elevator"}
FOOT_OUI = {"yes", "designated", "permissive", "official", "destination"}
INTERDIT = {"no", "private"}
TROTTOIR = {"both", "left", "right", "yes"}
TAGS = ["highway", "name", "access", "foot", "service", "tunnel", "area", "indoor",
        "sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right"]


def a_un_trottoir(t):
    """True si un trottoir est noté SUR la voie (pas cartographié à part)."""
    return (t.get("sidewalk") in TROTTOIR
            or "yes" in (t.get("sidewalk:both"), t.get("sidewalk:left"), t.get("sidewalk:right")))


def raison_exclusion(t):
    """Première règle qui exclut la voie (None = gardée). L'ordre est celui de la cascade."""
    hw, foot = t.get("highway"), t.get("foot")
    if hw in NON_CONSTRUIT:
        return "01 non construite / hors usage"
    if hw in TYPE_EXCLU:
        return "02 type exclu (platform, busway…)"
    if t.get("area") == "yes":
        return "03 aire (area=yes)"
    if hw in INTERIEUR or t.get("indoor") not in (None, "no"):
        return "04 intérieur"
    if t.get("service") == "private":
        return "05 service=private"
    if foot in INTERDIT:
        return "06 foot interdit"
    if foot not in FOOT_OUI and t.get("access") in INTERDIT:
        return "07 access interdit"
    if foot not in FOOT_OUI and hw in AUTOROUTE:
        return "08 autoroute"
    if foot not in FOOT_OUI and hw in TRUNK and not a_un_trottoir(t):
        return "09 trunk sans trottoir"
    if t.get("tunnel") in ("yes", "culvert") and hw not in CHEMIN_PIETON and foot not in FOOT_OUI:
        return "10 tunnel routier"
    return None


def lire_voies_osm(fichier, crs):
    """Lit le JSON Overpass (voies avec géométrie et nœuds) et renvoie un GeoDataFrame dans `crs`,
    avec les tags utiles, la raison d'exclusion éventuelle et la longueur (m)."""
    voies = [e for e in json.loads(fichier.read_text(encoding="utf-8"))["elements"] if e.get("type") == "way"]
    lignes = []
    for v in voies:
        coords = [(p["lon"], p["lat"]) for p in v.get("geometry", []) if p]   # p vide = nœud hors emprise
        if len(coords) >= 2 and len(coords) == len(v.get("nodes", [])):
            t = v.get("tags", {})
            ligne = {cle: t.get(cle) for cle in TAGS}
            ligne.update({"osm_id": v["id"], "raison": raison_exclusion(t), "noeuds": v["nodes"],
                          "geometry": LineString(coords)})
            lignes.append(ligne)
    osm = gpd.GeoDataFrame(lignes, crs=4326).to_crs(crs)
    osm["longueur"] = osm.length
    return osm, len(voies)


def ajouter_blocs(reseau):
    """Ajoute la colonne `bloc` (bloc connecté par les nœuds OSM partagés) et renvoie l'identifiant
    du plus grand bloc (en longueur)."""
    ids = {n: i for i, n in enumerate({n for ns in reseau["noeuds"] for n in ns})}
    a = [ids[n] for ns in reseau["noeuds"] for n in ns[:-1]]
    b = [ids[n] for ns in reseau["noeuds"] for n in ns[1:]]
    graphe = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(ids), len(ids)))
    _, etiquette = connected_components(graphe, directed=False)
    reseau["bloc"] = [etiquette[ids[ns[0]]] for ns in reseau["noeuds"]]
    return reseau.groupby("bloc")["longueur"].sum().idxmax()


def contour_plein(poly):
    """Le même espace sans ses trous (bâtiments enclavés) : seul le contour extérieur compte."""
    parties = getattr(poly, "geoms", [poly])
    return unary_union([Polygon(p.exterior) for p in parties if p.geom_type == "Polygon"])


def points_entrees(ev, reseau, penetration_m):
    """Points d'entrée ponctuelle d'un espace vert.
    1. On ne regarde que le contour EXTÉRIEUR (les trous, ex. un théâtre dans un parc, ne sont pas des entrées).
    2. On prend toutes les voies du réseau à l'intérieur de l'espace et on les regroupe en morceaux RELIÉS
       (une allée découpée en plusieurs voies OSM forme un seul morceau : extrémités communes, au cm près).
    3. Un croisement du contour est une entrée si le morceau relié qui part de ce point atteint l'intérieur
       de l'espace rétréci de `penetration_m` (un trottoir qui longe la clôture ne l'atteint pas).
    `ev` doit avoir une colonne id_ev. Renvoie un GeoDataFrame de points (id_ev, geometry)."""
    pleins = ev[["id_ev"]].copy()
    pleins = gpd.GeoDataFrame(pleins, geometry=ev.geometry.apply(contour_plein), crs=ev.crs)
    paires = gpd.sjoin(reseau[["geometry"]], pleins, predicate="intersects")
    points = []
    for id_ev, groupe in paires.groupby("id_ev"):
        plein = pleins.geometry.iloc[id_ev]
        coeur = plein.buffer(-penetration_m) if penetration_m > 0 else plein
        lignes = list(groupe.geometry)
        dedans = unary_union([l.intersection(plein) for l in lignes])   # voies coupées à la limite et aux croisements
        segments = [g for g in getattr(dedans, "geoms", [dedans]) if g.geom_type == "LineString" and g.length > 0]
        if not segments:
            continue
        # Morceaux reliés : deux segments qui partagent une extrémité (au cm près) sont dans le même morceau
        parent = list(range(len(segments)))

        def racine(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        extremites = {}
        for i, seg in enumerate(segments):
            for x, y in (seg.coords[0], seg.coords[-1]):
                cle = (round(x, 2), round(y, 2))
                if cle in extremites:
                    parent[racine(i)] = racine(extremites[cle])
                else:
                    extremites[cle] = i
        shapely.prepare(coeur)
        profonds = {racine(i) for i, touche in enumerate(shapely.intersects(coeur, segments)) if touche}
        if not profonds:
            continue
        # Les croisements de la limite sont des extrémités de segments : on garde ceux d'un morceau profond
        cles = list(extremites)
        sur_limite = shapely.dwithin(plein.boundary, shapely.points(cles), 0.01)
        for (x, y), limite in zip(cles, sur_limite):
            if limite and racine(extremites[(x, y)]) in profonds:
                points.append({"id_ev": id_ev, "geometry": Point(x, y)})
    pts = gpd.GeoDataFrame(points, columns=["id_ev", "geometry"], geometry="geometry", crs=ev.crs)
    # Un même croisement peut venir de deux voies qui se touchent sur la limite : on dédoublonne
    if len(pts):
        cle = list(zip(pts["id_ev"], pts.geometry.x.round(1), pts.geometry.y.round(1)))
        pts = pts.loc[~pd.Series(cle, index=pts.index).duplicated()]
    return pts


def compter_entrees(ev, reseau, seuil_diffus_m, penetration_m, fermes=()):
    """Pour chaque espace vert : nombre d'entrées ponctuelles (voir points_entrees) ; sinon entrée diffuse
    si une voie passe à moins de `seuil_diffus_m` ; sinon injoignable.
    `fermes` : pgs_id des espaces vérifiés fermés à l'œil (config.EV_FERMES_PGS_ID) -> toujours injoignables.
    Renvoie ev avec les colonnes id_ev, entrees_ponctuelles, distance_reseau_m et type_entree."""
    ev = ev.reset_index(drop=True).copy()
    ev["id_ev"] = ev.index
    pts = points_entrees(ev, reseau, penetration_m)
    ev["entrees_ponctuelles"] = ev["id_ev"].map(pts.groupby("id_ev").size()).fillna(0).astype(int)
    proches = gpd.sjoin_nearest(ev[["id_ev", "geometry"]], reseau[["geometry"]], distance_col="d")
    ev["distance_reseau_m"] = ev["id_ev"].map(proches.groupby("id_ev")["d"].min())
    ev["type_entree"] = np.where(ev["entrees_ponctuelles"] > 0, "ponctuelle",
                                 np.where(ev["distance_reseau_m"] <= seuil_diffus_m, "diffuse", "injoignable"))
    if fermes:
        ev.loc[ev["pgs_id"].astype(str).isin([str(f) for f in fermes]), "type_entree"] = "injoignable"
    return ev

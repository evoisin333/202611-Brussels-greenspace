# Tableau des données — livrable de la phase 1 (audit)

Chaleur urbaine et espaces verts à Bruxelles · Emma Voisin · clôture de l'audit le 20/11/2026

Toutes les sources indispensables existent, se téléchargent par script et passent leurs contrôles. Toutes les licences sont notées.

## Sources

| # | Donnée | Producteur | Version / date | Accès (script) | Licence | Audit (script : résultat) | Statut |
|---|---|---|---|---|---|---|---|
| 1 | Landsat 8 et 9, Collection 2 Level-2 (LST `lwir11`, `qa`, `cdist`, `qa_pixel`, `red`, `nir08`) | USGS, via Microsoft Planetary Computer (STAC `landsat-c2-l2`) | Étés 2013-2025 au catalogue ; 24 passages clairs 2020-2025 | 01 (catalogue), 05 (passage test) | Domaine public, citer l'USGS (DOI 10.5066/P9OGBGM6) | 01 : 16 PASS ; 04 : 7 PASS, **GO** (24 passages ≥ 90 %) ; 06 : 17 PASS | Vérifié |
| 2 | Contour de la Région | UrbIS (Paradigm), `urbisvector:Region` | Téléchargé le 18/11/2026 | 02 | Licence open data du SPF Finances (plan cadastral), d'après la fiche Geobru « Administrative units » : réutilisation et œuvres dérivées permises ; mentionner le SPF Finances, la licence et les modifications | 03 : 7 PASS (162,42 km²) | Vérifié |
| 3 | Secteurs statistiques au 01/01/2026 | Statbel | 749 secteurs bruxellois (découpage REDEGEO) | 07 | CC BY 4.0 (Statbel) | 08 : 19 PASS (avec 4 à 6) | Vérifié |
| 4 | Population par secteur 2026 (et 2025 « NEW ») | Statbel | 1er janvier 2026 (et 2025), nouveau découpage | 07 | CC BY 4.0 (Statbel) | 08 : total = officiel (1 255 834), toutes les jointures OK | Vérifié |
| 5 | Grille de population à cellules variables | Statbel (Datalab) | 01/01/2025, mailles de 125 m à 1 km, EPSG:3035 | 07 | CC BY 4.0 (Statbel) | 08 : −0,44 % contre les secteurs ; 76 % de la population en mailles de 125 m | Vérifié (données expérimentales) |
| 6 | Espaces verts accessibles au public | Bruxelles Environnement, `public_green_spaces` | Version 2024 | 09 | CC-BY (citer « Bruxelles Environnement / Leefmilieu Brussel ») | 10 : 15 PASS, 1 FAIL **expliqué** (surface 2024 > 2023 : nouvelle typologie) | Vérifié |
| 7 | Zones de carence en espaces verts | Bruxelles Environnement, `green_space_deficiency_zone` | Données publiées (validation seulement) | 09 | CC-BY | 10 : 41,7 km² (25,7 % de la Région) | Vérifié |
| 8 | Réseau de voies | OpenStreetMap, via l'API Overpass | Figé au 01/11/2026 (paramètre `date`) | 11 | ODbL (« © OpenStreetMap contributors ») | 12 : 8 PASS (couverture 99,77 %, connexité 99,18 %) | Vérifié |
| 9 | Axes de rues (référence de couverture) | UrbIS (Paradigm), `urbisvector:StreetAxes` | Téléchargé le 20/11/2026 | 11 | CC-0 (UrbIS Réseaux de transport) | 12 : CRS et emprise OK | Vérifié |

Les requêtes exactes (URL, paramètres, dates) sont notées par chaque script dans un fichier `requete*.txt` à côté des données brutes (`data/brut/bruxelles/`).

## Ce que l'audit a établi (chiffres clés)

| Donnée | Chiffre | Source |
|---|---|---|
| Passages Landsat clairs (≥ 90 % de la Région), juin-août 2020-2025 | 24 (≥ 3 par été) | audit 04 |
| Résolution réelle de la bande thermique | 100 m (livrée à 30 m) | catalogue STAC |
| Passage test 13/07/2025 : LST médiane de la Région | 38,0 °C (forêt de Soignes 26,3 °C, Pentagone 41,6 °C) | audit 06 |
| Surface de la Région | 162,42 km² | audits 03 et 08 |
| Population de la Région au 01/01/2026 | 1 255 834, dont 2 785 en secteur inconnu (0,22 %) | audit 08 |
| Espaces verts accessibles (toute la couche 2024) | 1 305 espaces, 3 466 ha | audit 10 |
| Réseau piéton OSM provisoire | 7 284 km | audit 12 |

## Pièges trouvés pendant l'audit

| Piège | Comment on l'a vu | Ce qu'on fait |
|---|---|---|
| Codes NIS lus comme des nombres (`04000` → `4000`) | Inspection du contour UrbIS | Codes toujours lus comme du texte |
| Une date de passage = deux scènes (lignes 024 et 025) | Audit du catalogue | Raisonner en passages, assembler les lignes |
| `QA_PIXEL` sans valeur vide déclarée | Part claire de 1,79 % au lieu de 99,99 % (contrôle croisé) | Valeur vide = 1 déclarée explicitement |
| Fichiers Statbel d'encodages différents (UTF-8 et latin-1) | Inspection du script 07 | Encodage précisé par fichier |
| Colonne `subtype_f` (documentation : `sub_type_f`) | Audit 10 | Se fier aux données, pas à la documentation |
| `area_m2` en hectares | Rapport de 9 999 avec la surface calculée | Surfaces recalculées depuis la géométrie |
| WFS Bruxelles Environnement en version 1.1.0 | Erreur « TYPENAME is mandatory » | Paramètres adaptés à la version annoncée |
| Overpass saturé (504, 502) | Téléchargement OSM | Tuiles + nouveaux essais |

# Note de cadrage v2 — Chaleur urbaine et espaces verts à Bruxelles

20 novembre 2026 · Emma Voisin · Statut : **question figée** à la clôture de l'audit (phase 1). Remplace la v1 du 17/11/2026.

## Question (figée)

**Quels secteurs statistiques bruxellois cumulent une forte chaleur de surface en été et un faible accès à pied à un espace vert public, et combien de personnes y vivent ?**

On parle d'associations entre secteurs, jamais de causes ni d'individus.

## Ce qui a changé depuis la v1, et pourquoi

| v1 (17/11) | v2 (20/11) | Raison |
|---|---|---|
| Accès : 300 m à vol d'oiseau, espaces de 0,5 ha et 1 ha | Accès : définition de Bruxelles Environnement (< 1 ha à 200 m, ≥ 1 ha à 400 m) **en cheminement réel** ; variante à vol d'oiseau en comparaison | Les gens doivent pouvoir s'y rendre à pied (canal, voies ferrées) ; méthode officielle bruxelloise, validation directe |
| Population répartie uniformément ou sur les bâtiments | Population Statbel 2026 placée finement (grille 2025 à cellules variables ou bâtiments, choix en phase 2) | La grille existe : 76 % des Bruxellois en mailles de 125 m |
| Réseau de rues en bonus (pgRouting) | Réseau piéton OSM dans le cœur du projet | Conséquence du cheminement réel |
| Secteurs « à confirmer » | 749 secteurs au 01/01/2026 (découpage REDEGEO) | Population 2026 publiée sur ce découpage |

## Périmètre

- Région de Bruxelles-Capitale (19 communes, 162,42 km²). Unité : secteur statistique (749) ; test au niveau quartier (MAUP).
- Chaleur : LST relative d'été (médiane, passage par passage, des écarts à la médiane régionale), Landsat 8 et 9 Tier 1, juin-août 2020-2025. Analyse en coupe.
- Accès : part de la population de chaque secteur **sans** espace vert accessible à moins de 200 m (espace < 1 ha) ni à moins de 400 m (espace ≥ 1 ha), distances à pied sur le réseau OSM ; même calcul à vol d'oiseau.
- Population : Statbel au 1er janvier 2026.
- Hors périmètre minimal : température de l'air, nuit, tendance, autres villes, âge, revenu, règle 3-30-300 (bonus prioritaire).

## Données (toutes vérifiées, voir `tableau_donnees.md`)

Landsat C2 L2 (USGS, domaine public) · contour UrbIS · secteurs, population et grille Statbel (CC BY 4.0) · espaces verts accessibles et zones de carence Bruxelles Environnement (CC-BY) · réseau OSM figé au 01/11/2026 (ODbL) · axes de rues UrbIS (CC-0) · contour de la Région : licence open data du SPF Finances.

## Critères de réussite

1. Chaque donnée indispensable a le statut « vérifié » : **atteint**.
2. La chaîne tourne de zéro depuis le dépôt (scripts numérotés, chemins relatifs, `environment.yml`).
3. Validation croisée : la part de Bruxellois en carence (cheminement réel) est comparable aux ~22 % publiés par Bruxelles Environnement (données 2023, population 2021) ; tolérance fixée en phase 2, avant le calcul. Contrôle de sens : carence à vol d'oiseau ≤ carence à pied.
4. Statistiques tenant compte de l'autocorrélation spatiale (indice de Moran, tests par permutation).
5. Chaque chiffre publié vient d'un CSV de résultats ; relecture croisée des chiffres avant publication.
6. Section « Limites » dans la StoryMap et le README.

## Décisions à prendre en phase 2 (avant tout résultat)

- Chaleur : 24 passages clairs seuls ou tous les pixels clairs ; seuil sur `ST_QA` ; exclusion des pixels proches des nuages ; masque de l'eau ; sensibilité juin/août ; référence bibliographique de la LST relative.
- Espaces verts : filtre (sous-types, statut foncier, `pct_veg` > 50 %) + sensibilité « toute la couche » contre « filtre BE ».
- Réseau : filtre piéton définitif ; grand bloc connecté seul ; définition des entrées de parcs ; outil (pgRouting ou Python).
- Population : grille ou bâtiments ; seuil minimal de population par secteur (71 secteurs < 50 hab. = 0,04 % de la population).
- Définition de « forte chaleur » et « faible accès » (seuils ou classes) ; CRS de calcul ; tests statistiques.

## Hypothèses

- La LST de fin de matinée suffit pour classer les secteurs entre eux (pas pour mesurer l'exposition des habitants).
- Le réseau OSM, couvrant 99,77 % des rues officielles et connecté à 99,18 %, représente bien les trajets à pied.
- La couche 2024 des espaces verts accessibles décrit bien l'offre réelle, une fois filtrée.

## Risques restants

| Risque | Gravité | Parade |
|---|---|---|
| Définition des entrées de parcs | Haute | Approche documentée (points où le réseau entre dans le parc) + sensibilité |
| Choix du filtre des espaces verts | Haute | Fixé avant calcul ; deux variantes publiées |
| Licence ArcGIS Pro (fin 30/11) | Moyenne | ArcGIS for Personal Use |
| Autocorrélation, MAUP, erreur écologique | Moyenne | Méthode fixée en phase 2 ; vocabulaire « secteurs » |
| Complexité du cheminement réel | Moyenne | Réduire le périmètre plutôt que les contrôles |

# Note de cadrage v1 — Chaleur urbaine et espaces verts à Bruxelles

17 novembre 2026 · Emma Voisin · Statut : provisoire, question figée seulement après l'audit (phase 1)

## Question (provisoire)
Quels secteurs bruxellois cumulent une forte chaleur de surface en été et un faible accès à un espace vert public, et combien de personnes y vivent ?
On parle d'associations par secteur, jamais de causes ni d'individus.

## Périmètre
- Région de Bruxelles-Capitale (19 communes). Unité : secteur statistique ; test au niveau quartier (MAUP).
- Étés (juin–août) 2020–2025, Landsat 8 et 9. Analyse en coupe, pas de tendance.
- Indicateurs : LST relative d'été (médiane, scène par scène, des écarts à la médiane régionale) ; NDVI ; part de la population à moins de 300 m d'un espace vert public (seuils 0,5 ha et 1 ha) ; population concernée.
- Hors périmètre minimal : température de l'air, nuit, distance par le réseau, tendance, autres villes, âge, revenu.

## Critères de réussite (écrits avant les données)
1. Chaque donnée indispensable a le statut « vérifié » (accès par script, couverture, période, licence notée).
2. La chaîne tourne de zéro depuis le dépôt (scripts numérotés, chemins relatifs, environment.yml, aucune étape manuelle non documentée).
3. Validation croisée : notre part de population à moins de 300 m retrouve les ordres de grandeur IBSA par quartier (seuil d'écart fixé en phase 2, avant calcul) ; sinon on explique pourquoi.
4. Statistiques tenant compte de l'autocorrélation spatiale (Moran, permutations).
5. Chaque chiffre publié vient d'un CSV de résultats ; relecture croisée des chiffres avant publication.
6. Section « Limites » dans la StoryMap et le README.

## Livrables
StoryMap en anglais (6 sections, charte « Belgium's Changing Seasons ») ; dépôt GitHub (SQL + Python, schéma de la base, README anglais, commentaires français) ; posts LinkedIn FR.
Cartes dans ArcGIS Pro (ArcGIS for Personal Use après le 30/11/2026) ; données préparées en Python/SQL ; symbologies en .lyrx dans le dépôt.

## Hypothèses
- Assez d'images d'été claires sur Bruxelles en 2020–2025.
- Population et limites des secteurs sur le même découpage et la même année.
- La couche « espaces verts accessibles au public » de Bruxelles Environnement représente bien l'accès réel.
- Une LST Landsat de fin de matinée suffit pour classer les secteurs entre eux (pas l'exposition des habitants).

## Risques
| Risque | Gravité | Parade |
|---|---|---|
| Trop peu d'images claires | Bloquante | Critère GO/NO-GO en phase 1 ; repli 2013–2025 ou mai–septembre |
| Découpages incohérents (REDEGEO) | Haute | Taux de jointure par code de secteur dès l'audit |
| Licence ArcGIS Pro (fin 30/11) | Moyenne | Personal Use ; préparation des données hors ArcGIS |
| Autocorrélation, MAUP, erreur écologique | Moyenne | Méthode fixée en phase 2 ; vocabulaire « secteurs » |
| Effet de bord (parcs flamands) | Moyenne | Écrit comme limite dans la version minimale |
| Périmètre qui gonfle | Moyenne | Aucun bonus avant la StoryMap minimale |

## Bonus (après la StoryMap minimale)
1. Règle 3-30-300 (choisi par Emma comme bonus prioritaire).
2. Vulnérabilité : part de personnes âgées / jeunes enfants par secteur (donnée à vérifier à l'audit).
3. Revenu médian fiscal, avec les limites IBSA (Focus n° 14, 2016 : revenus exonérés des fonctionnaires internationaux, RIS, déclarations nulles).
4. Autres bonus de la passation (pgRouting, canicule, tendance, tableau de bord, autre ville).

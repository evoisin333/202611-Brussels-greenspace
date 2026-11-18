# Journal des décisions — Chaleur urbaine et espaces verts à Bruxelles

| Date | Phase | Choix | Raison | Alternative écartée | Limite |
|---|---|---|---|---|---|
| 17/11/2026 | 0 | Question provisoire, figée après l'audit | Leçon du projet eau (périmètre infaisable découvert tard) | Figer la question maintenant | Note de cadrage révisable |
| 17/11/2026 | 0 | Audit dans l'ordre du risque : Landsat → secteurs/population → espaces verts | Sources qui peuvent tuer le projet d'abord | Ordre du tableau | — |
| 17/11/2026 | 0 | Catalogue STAC Planetary Computer en premier choix d'accès Landsat | Recherche sans compte, lecture partielle des COG | USGS M2M (compte requis) | Dépendance à un service tiers |
| 17/11/2026 | 0 | Critères GO/NO-GO de l'audit écrits avant les données | Éviter d'ajuster les seuils au résultat | Décider au vu des données | Seuils en partie arbitraires |
| 17/11/2026 | 0 | LST relative : médiane des écarts à la médiane régionale, scène par scène | Les secteurs ne sont pas vus les mêmes jours (nuages) | Médiane des LST absolues | Comparaison entre secteurs, pas de °C absolus ; à sourcer en phase 2 |
| 17/11/2026 | 0 | Secteur statistique comme unité, test par quartier | Unité la plus fine avec population | Quartier seul | MAUP à tester |
| 17/11/2026 | 0 | Cartes dans ArcGIS Pro ; données en Python/SQL ; symbologies .lyrx | Compétence ArcGIS + reproductibilité | Cartes Python/QGIS | Personal Use nécessaire après le 30/11 |
| 17/11/2026 | 0 | Parcs flamands : limite écrite (version minimale) | Pas de couche ouverte vérifiée | Les charger d'office | Accès sous-estimé au bord de la Région |
| 17/11/2026 | 0 | Pas de date de publication ; réduire le périmètre plutôt que les contrôles | Qualité d'abord | Échéance fixe | — |
| 17/11/2026 | 0 | Environnement conda « chaleur » séparé de « geo » | Protéger la reproductibilité du dépôt Belgique | Réutiliser « geo » | — |
| 17/11/2026 | 0 | PostgreSQL/PostGIS installés en phase 3 | Inutiles pour l'audit | Installation immédiate | — |
| 17/11/2026 | 0 | Section 5 = population concernée ; âge puis revenu en bonus | Robuste, pas de nouvelle donnée ni de biais fiscal | Revenu dans la version minimale | Pas d'angle justice environnementale en version minimale |
| 17/11/2026 | 0 | Règle 3-30-300 = bonus prioritaire | Prolonge directement l'analyse d'accès | Autres bonus d'abord | Après la StoryMap minimale seulement |
| 17/11/2026 | 1.0 | Dépôt GitHub `202611-Brussels-heat-greenspace`, dossier local `Portfolio\Brussels greenspace\` | Même convention que le dépôt Belgique | — | Espace dans le chemin : guillemets obligatoires |
| 17/11/2026 | 1.0 | Numérotation unique dans l'ordre d'exécution, dossiers par phase | Ordre de lancement lisible, rôle clair | Numérotation par dossier | Renuméroter = local et GitHub en même temps |
| 17/11/2026 | 1.0 | Un `README.md` dans chaque dossier | GitHub ignore les dossiers vides ; documente le dépôt | `.gitkeep` vide | — |
| 17/11/2026 | 1.0 | Tous les paquets prévisibles installés en une fois | Versions compatibles dès le départ | Installer au fur et à mesure | Quelques paquets inutiles avant la phase 3 |
| 17/11/2026 | 1.0 | Deux fichiers : `environment.yml` (portable, tenu à la main) + `environment_lock.yml` (versions exactes) | Réinstallable partout et traçable | Un seul fichier ; réexport `--from-history` | Lock surtout valable sous Windows ; tout nouveau paquet ajouté à la main au .yml |
| 17/11/2026 | 1.0 | Ligne `prefix` retirée des fichiers d'environnement | Chemin local inutile ailleurs | La laisser | À refaire à chaque réexport |
| 17/11/2026 | 1.0 | `chaleur` recréé depuis `environment.yml` : OK | Test de reproductibilité | — | — |
| 17/11/2026 | 1.0 | Anomalie documentée : scipy 1.17.1 installé par conda (`INSTALLER = conda`) sans fiche `conda-meta`, donc listé « pypi » | Cause introuvable en un temps raisonnable ; aucun effet sur les calculs | Chercher plus loin | Signalé dans le README (Known issues) |
| 17/11/2026 | 1.0 | Lock corrigé à la main : `scipy=1.17.1` dans les dépendances conda, pas de section `pip:` | Recréer depuis le lock ne doit pas passer par PyPI | Garder `pip:` | À refaire à chaque réexport |
| 17/11/2026 | 1.0 | Plus de `conda install` ni de `pip install` dans `chaleur` : nouveau paquet → `environment.yml` → recréer l'environnement | conda ne suit pas scipy ; reteste la reproductibilité | Installer en place | Quelques minutes à chaque ajout |
| 17/11/2026 | 1.0 | À chaque réexport du lock : aucun `==`, aucun `- pip:`, aucun `prefix` | Détecter vite les problèmes | Pas de contrôle | — |
| 17/11/2026 | 1.0 | Paramètres (ville, emprise, années, chemins) dans `config.py` ; données dans `data/brut/<ville>/` et `data/travail/<ville>/` | Ville en paramètre, chemins relatifs | Paramètres dans chaque script | Emprise WGS84 provisoire (marge), limite exacte à l'audit 1.7 |
| 17/11/2026 | 1.0 | `data/` dans le dépôt local mais jamais uploadé : on glisse les dossiers un par un sur GitHub, sauf `data/` | L'upload web ignore `.gitignore` | Données hors du dossier du dépôt | Vigilance à chaque upload |

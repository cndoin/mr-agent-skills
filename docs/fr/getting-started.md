# Bien démarrer

Ce guide commence par la recherche bibliographique, vous laisse examiner les paires candidates, puis poursuit l’analyse MR.

## Prérequis

- Python 3.11/3.12 est recommandé et couvert par la CI. Le contrôle accepte 3.9–3.12 sauf 3.9.7 ; 3.9/3.10 ne sont pas couverts par la CI et 3.13+ est actuellement bloqué.
- R 4.3.4 ou ultérieur et les paquets indiqués dans [`../../references/environment.md`](../../references/environment.md).
- Le paquet amont `mragent` et un moteur LLM compatible.
- Un JWT OpenGWAS dans `MRAGENT_GWAS_TOKEN` ou `OPENGWAS_JWT`.

L’installateur copie uniquement les fichiers de la compétence ; il n’installe ni Python, ni R, ni les dépendances de MRAgent.

## Installer

```bash
python install.py --target all
```

Choisissez `claude`, `workbuddy` ou `codebuddy` avec `--target`. `python install.py --list` vérifie les métadonnées sans installer.

## Préparer l’environnement

Créez un environnement Python 3.11/3.12, installez `mragent==0.2.5`, configurez les paquets R et définissez les identifiants dans des variables d’environnement. Consultez [`../../references/environment.md`](../../references/environment.md) pour les commandes selon votre système. Ne collez pas de vrais identifiants dans les commandes, le code source ou des tickets publics.

Avant de consommer le quota LLM ou API, lancez le contrôle préalable :

```bash
python scripts/preflight.py --no-network
```

Le rapport signale les prérequis manquants sans afficher les valeurs des identifiants.

## Chercher, puis examiner

Prévisualisez les paramètres :

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

Lancez la recherche bibliographique :

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

Examinez `Exposure_and_Outcome.csv` dans le dossier d’exécution, modifiez les paires si nécessaire, puis poursuivez :

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

Chaque véritable exécution crée un nouveau dossier. `--dry-run` affiche la configuration sans le créer. Le lanceur vérifie la présence de `mr_run.csv` au lieu de se fier uniquement au code de sortie du processus.

## Modes

| Mode | Entrée requise | Objectif |
| --- | --- | --- |
| `O` | `--outcome` | Chercher des expositions candidates pour un résultat |
| `E` | `--exposure` | Chercher des résultats candidats pour une exposition |
| `OE` | `--exposure` et `--outcome` | Évaluer une paire définie |

## Extension des synonymes

L’extension UMLS est désactivée par défaut. L’API amont de MRAgent contient une clé UMLS et ne permet actuellement pas à ce lanceur de la remplacer. `--synonyms` active ce comportement amont. L’outil autonome `tools/mr_synonyms.py` exige votre propre `UMLS_API_KEY`.

## Interpréter les résultats avec prudence

Les estimations MR dépendent de la validité des instruments, du protocole d’étude, du chevauchement des échantillons et des données disponibles. Faites examiner les jeux de données et les diagnostics par un spécialiste. Les résultats constituent des éléments de recherche, pas un conseil clinique ni une preuve de causalité.

## Documentation complémentaire

- [`references/api.md`](../../references/api.md) — constructeur et étapes
- [`references/pitfalls.md`](../../references/pitfalls.md) — problèmes connus en amont
- [`references/environment.md`](../../references/environment.md) — configuration complète
- [`SECURITY.md`](../../SECURITY.md) — identifiants et risques connus

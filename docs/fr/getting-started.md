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

Choisissez `claude`, `workbuddy`, `codebuddy`, `codex` ou `deepseek` avec `--target`. Codex utilise par défaut `~/.codex/skills/mr-agent` et DeepSeek Harness `~/.dsh/skills/mr-agent` ; `CODEX_HOME` et `DSH_HOME` permettent de modifier ces chemins. `python install.py --list` vérifie les métadonnées et affiche les destinations sans installer.

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

## SMR / HEIDI (facultatif)

`tools/mr_smr.py` exécute SMR (Zhu et al. 2016 *Nat Genet*) et le test HEIDI sur données résumées, et répond à la question que TwoSampleMR ne peut pas traiter : **quel gène médiatise ce signal ?**

```bash
# 1. Préparez le binaire officiel smr (téléchargé et vérifié dans le cache global ; ou indiquez-en un avec SMR_BIN)
python tools/mr_smr.py fetch-binary
# 2. Vérifiez l’environnement et vos entrées
python tools/mr_smr.py preflight
# 3. Analysez : native n’a aucune dépendance, official pilote le binaire officiel
python tools/mr_smr.py analyze --engine native \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
python tools/mr_smr.py analyze --engine official \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
```

`--engine native` est une implémentation fondée uniquement sur la bibliothèque standard, dont le test SMR correspond à l’officiel **chiffre par chiffre** ; le `p_HEIDI` de HEIDI présente un écart connu sur les décimales (le sens concorde, et la sortie comme la documentation le signalent). La sous-commande `official` transmet telle quelle n’importe quelle option officielle : aucune capacité officielle ne manque. Les formats de données, les 48 options mappées et la calibration mesurée sont dans [`references/smr.md`](../../references/smr.md). Cette voie ne demande ni R, ni `mragent`, ni jeton OpenGWAS : seulement Python et vos données résumées cis-xQTL / GWAS.

## Extension des synonymes

L’extension UMLS est désactivée par défaut. L’API amont de MRAgent contient une clé UMLS et ne permet actuellement pas à ce lanceur de la remplacer. `--synonyms` active ce comportement amont. L’outil autonome `tools/mr_synonyms.py` exige votre propre `UMLS_API_KEY`.

## Interpréter les résultats avec prudence

Les estimations MR dépendent de la validité des instruments, du protocole d’étude, du chevauchement des échantillons et des données disponibles. Faites examiner les jeux de données et les diagnostics par un spécialiste. Les résultats constituent des éléments de recherche, pas un conseil clinique ni une preuve de causalité.

## Documentation complémentaire

- [`references/api.md`](../../references/api.md) — constructeur et étapes
- [`references/pitfalls.md`](../../references/pitfalls.md) — problèmes connus en amont
- [`references/environment.md`](../../references/environment.md) — configuration complète
- [`references/smr.md`](../../references/smr.md) — SMR / HEIDI : formats de données et les deux moteurs

- [`SECURITY.md`](../../SECURITY.md) — identifiants et risques connus

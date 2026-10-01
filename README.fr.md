<div align="center">

# MR Agent

### Des articles aux hypothèses vérifiables

Une compétence d’agent open source pour la recherche en randomisation mendélienne.

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md)

![Illustration du projet MR Agent](assets/mr-agent-cover.svg)

</div>

MR Agent transforme [MRAgent](https://github.com/xuwei1997/MRAgent) en parcours vérifiable : recherche bibliographique dans PubMed, consultation des jeux GWAS, exécution de TwoSampleMR avec R et examen des résultats. Le projet ajoute le contrôle de l’environnement, des répertoires isolés, une sortie JSON structurée et des outils pour examiner les CSV intermédiaires. Les méthodes statistiques sont fournies par MRAgent et ses dépendances R.

## Modes

| Mode | Utilisation |
| --- | --- |
| `O` | Partir d’un résultat et chercher des expositions candidates |
| `E` | Partir d’une exposition et chercher des résultats candidats |
| `OE` | Évaluer une paire exposition–résultat donnée |

Il est recommandé d’examiner les paires candidates après la recherche bibliographique et avant de poursuivre l’analyse.

## Prérequis

- Python 3.11/3.12 est recommandé et couvert par la CI. Le contrôle accepte 3.9–3.12 sauf 3.9.7 ; 3.9/3.10 ne sont pas couverts par la CI et 3.13+ est bloqué pour le moment.
- R 4.3.4 ou ultérieur et les paquets listés dans [`references/environment.md`](references/environment.md).
- Pour une analyse complète : paquet amont `mragent`, moteur LLM et JWT OpenGWAS.

## Installation et démarrage

```bash
python install.py --target all
python scripts/preflight.py --no-network
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

Examinez `Exposure_and_Outcome.csv` avant de lancer les étapes suivantes. Chaque analyse réelle utilise un nouveau répertoire. `--dry-run` affiche uniquement la configuration et ne crée pas de répertoire.

## Sécurité et limites

- Les estimations MR dépendent des instruments, du protocole d’étude, du chevauchement des échantillons et des données disponibles. Elles ne prouvent pas la causalité, ne remplacent pas une expertise et ne constituent pas un conseil clinique.
- L’extension des synonymes UMLS est désactivée par défaut. Avec `--synonyms`, MRAgent utilise sa clé UMLS intégrée ; l’outil autonome de synonymes exige votre propre clé.
- Le dépôt n’inclut ni statistiques GWAS ni fichier CSV de catalogue OpenGWAS.

## Guide et vérifications

- [Guide en français](docs/fr/getting-started.md) · [Guides dans toutes les langues](docs/)
- `python scripts/selftest.py --quick` · `python install.py --list`

Les tests locaux vérifient les scripts auxiliaires ; ils ne lancent pas d’analyse MR complète ni de services en direct.

## Citation et licence

Pour citer MRAgent : Xu et al., *Briefings in Bioinformatics* (2025), [doi:10.1093/bib/bbaf140](https://doi.org/10.1093/bib/bbaf140). Cette compétence est sous licence MIT et MRAgent sous Apache-2.0. Voir [`NOTICE`](NOTICE) pour les attributions.

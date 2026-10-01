<div align="center">

# MR Agent

### De los artículos a hipótesis verificables

Una skill de agente de código abierto para la investigación de aleatorización mendeliana.

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md)

![Ilustración del proyecto MR Agent](assets/mr-agent-cover.svg)

</div>

MR Agent convierte [MRAgent](https://github.com/xuwei1997/MRAgent) en un flujo revisable: búsqueda bibliográfica en PubMed, consulta de conjuntos GWAS, ejecución de TwoSampleMR mediante R y revisión de resultados. Añade comprobaciones del entorno, directorios aislados, salida JSON estructurada y herramientas para revisar los CSV intermedios. Los métodos estadísticos pertenecen a MRAgent y sus dependencias de R.

## Modos

| Modo | Uso |
| --- | --- |
| `O` | Partir de un resultado y buscar exposiciones candidatas |
| `E` | Partir de una exposición y buscar resultados candidatos |
| `OE` | Evaluar una pareja exposición–resultado especificada |

Se recomienda revisar las parejas candidatas después de la búsqueda bibliográfica y antes de seguir con el análisis.

## Requisitos

- Se recomiendan Python 3.11/3.12, cubiertos por CI. La comprobación acepta 3.9–3.12 salvo 3.9.7; 3.9/3.10 no están en CI y 3.13+ se bloquea por ahora.
- R 4.3.4 o posterior y los paquetes indicados en [`references/environment.md`](references/environment.md).
- Para un análisis completo: paquete upstream `mragent`, backend LLM y JWT de OpenGWAS.

## Instalación y primeros pasos

```bash
python install.py --target all
python scripts/preflight.py --no-network
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

Revisa `Exposure_and_Outcome.csv` antes de ejecutar los pasos posteriores. Cada ejecución real usa un directorio nuevo. `--dry-run` solo muestra la configuración y no crea el directorio.

## Seguridad y límites

- Las estimaciones de MR dependen de los instrumentos, el diseño del estudio, el solapamiento de muestras y los datos disponibles. No prueban causalidad, no sustituyen la revisión experta y no son consejo clínico.
- La expansión de sinónimos UMLS está desactivada por defecto. Con `--synonyms`, MRAgent usa su clave UMLS integrada; la herramienta independiente de sinónimos exige una clave propia.
- El repositorio no incluye estadísticas GWAS ni el índice CSV de OpenGWAS.

## Guía y verificación

- [Guía en español](docs/es/getting-started.md) · [Guías en todos los idiomas](docs/)
- `python scripts/selftest.py --quick` · `python install.py --list`

Las pruebas locales verifican los scripts auxiliares; no ejecutan un análisis MR completo ni servicios en directo.

## Cita y licencia

Para citar MRAgent: Xu et al., *Briefings in Bioinformatics* (2025), [doi:10.1093/bib/bbaf140](https://doi.org/10.1093/bib/bbaf140). Esta skill tiene licencia MIT y MRAgent Apache-2.0. Consulta [`NOTICE`](NOTICE) para atribuciones.

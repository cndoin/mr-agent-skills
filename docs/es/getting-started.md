# Primeros pasos

Esta guía ejecuta primero la búsqueda bibliográfica, permite revisar los pares candidatos y después continúa el análisis MR.

## Requisitos

- Se recomiendan Python 3.11/3.12, cubiertos por CI. La comprobación previa acepta 3.9–3.12 excepto 3.9.7; 3.9/3.10 no están en CI y 3.13+ se bloquea actualmente.
- R 4.3.4 o posterior y los paquetes indicados en [`../../references/environment.md`](../../references/environment.md).
- El paquete upstream `mragent` y un backend LLM compatible.
- Un JWT de OpenGWAS en `MRAGENT_GWAS_TOKEN` o `OPENGWAS_JWT`.

El instalador solo copia los archivos de la skill; no instala Python, R ni las dependencias de MRAgent.

## Instalar

```bash
python install.py --target all
```

Elige `claude`, `workbuddy`, `codebuddy`, `codex` o `deepseek` con `--target`. Codex usa `~/.codex/skills/mr-agent` y DeepSeek Harness `~/.dsh/skills/mr-agent` de forma predeterminada; `CODEX_HOME` y `DSH_HOME` permiten cambiar las rutas. `python install.py --list` valida los metadatos y muestra los destinos sin instalar.

## Preparar el entorno

Crea un entorno Python 3.11/3.12, instala `mragent==0.2.5`, configura los paquetes de R y define las credenciales como variables de entorno. Consulta [`../../references/environment.md`](../../references/environment.md) para instrucciones específicas de cada plataforma. No pegues credenciales reales en comandos, código o incidencias públicas.

Antes de consumir cuota de LLM o API, ejecuta la comprobación previa:

```bash
python scripts/preflight.py --no-network
```

El informe señala los requisitos pendientes sin revelar los valores de las credenciales.

## Buscar y revisar

Previsualiza los parámetros:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

Ejecuta la búsqueda:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

Revisa `Exposure_and_Outcome.csv` en el directorio de ejecución, modifica las parejas si hace falta y continúa:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

Cada ejecución real crea un directorio nuevo. `--dry-run` muestra la configuración sin crearlo. Para informar de éxito, el ejecutor comprueba `mr_run.csv` en vez de fiarse solo del código de salida del proceso.

## Modos

| Modo | Entrada requerida | Objetivo |
| --- | --- | --- |
| `O` | `--outcome` | Buscar exposiciones candidatas para un resultado |
| `E` | `--exposure` | Buscar resultados candidatos para una exposición |
| `OE` | `--exposure` y `--outcome` | Evaluar una pareja específica |

## SMR / HEIDI (opcional)

`tools/mr_smr.py` ejecuta SMR (Zhu et al. 2016 *Nat Genet*) y la prueba HEIDI sobre datos resumen, y responde a la pregunta que TwoSampleMR no puede: **¿qué gen media esta señal?**

```bash
# 1. Prepara el binario oficial smr (se descarga y verifica en la caché global; o indica uno existente con SMR_BIN)
python tools/mr_smr.py fetch-binary
# 2. Comprueba el entorno y tus entradas
python tools/mr_smr.py preflight
# 3. Analiza: native no tiene dependencias, official usa el binario oficial
python tools/mr_smr.py analyze --engine native \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
python tools/mr_smr.py analyze --engine official \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
```

`--engine native` es una implementación solo con la biblioteca estándar cuyo test SMR coincide con el oficial **dígito a dígito**; el `p_HEIDI` de HEIDI presenta una diferencia conocida en los decimales (la dirección coincide y tanto la salida como la documentación lo indican). El subcomando `official` permite pasar cualquier opción oficial tal cual, sin omitir ninguna capacidad. Los formatos de datos, los 48 flags mapeados y la calibración medida están en [`references/smr.md`](../../references/smr.md). Esta vía no necesita R, ni `mragent`, ni token de OpenGWAS: solo Python y tus datos resumen cis-xQTL / GWAS.

## Expansión de sinónimos

La expansión UMLS está desactivada por defecto. La API upstream de MRAgent incorpora una clave UMLS y actualmente no permite reemplazarla desde este ejecutor. `--synonyms` activa ese comportamiento. La herramienta independiente `tools/mr_synonyms.py` requiere tu propia `UMLS_API_KEY`.

## Interpretar con cuidado

Las estimaciones MR dependen de la validez de los instrumentos, el diseño del estudio, el solapamiento de muestras y los datos disponibles. Revisa los conjuntos de datos y diagnósticos con una persona experta. Los resultados son evidencia de investigación, no consejo clínico ni prueba de causalidad.

## Más documentación

- [`references/api.md`](../../references/api.md) — constructor y pasos
- [`references/pitfalls.md`](../../references/pitfalls.md) — problemas conocidos de upstream
- [`references/environment.md`](../../references/environment.md) — configuración completa
- [`references/smr.md`](../../references/smr.md) — SMR / HEIDI: formatos de datos y los dos motores

- [`SECURITY.md`](../../SECURITY.md) — credenciales y riesgos conocidos

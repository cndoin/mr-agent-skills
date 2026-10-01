# Security Policy

## Reporting a Vulnerability

Please do not report security issues in public issues. Use GitHub's private vulnerability reporting feature from the repository's **Security** tab. Include the affected version, reproduction steps, and practical impact, especially any risk of credential disclosure, path traversal, or a false-success result.

## Credential Handling

This project may use an OpenGWAS JWT, an LLM API key, and (for standalone synonym lookup) a UMLS API key. Supply credentials through environment variables whenever possible. Never commit real credentials, paste them into public issues, or share an entire run directory without reviewing it.

The runner accepts `MRAGENT_GWAS_TOKEN` or `OPENGWAS_JWT`, and `MRAGENT_AI_KEY` or `OPENAI_API_KEY` for the corresponding integrations. The standalone synonym tool requires the user's own UMLS key. UMLS synonym expansion is disabled by default in the full workflow because upstream MRAgent embeds its own key and does not currently expose a replacement parameter.

## Known Upstream File Handling

Upstream MRAgent writes the OpenGWAS JWT into a generated `test.R` file in its working directory. This project attempts to redact credentials from `test.R` and `run.log` when a run finishes, and the result exporter excludes those files by default. A forced process termination can bypass cleanup. Review and remove `test.R` before sharing a run directory, and do not use the exporter's `--no-exclude` option unless you have checked the files.

Redaction covers the known file locations; it is not a recursive scan of every output file. The project does not collect or upload analysis data. Network requests are made only to services required by the configured workflow, such as PubMed, OpenGWAS, UMLS, and the user's LLM endpoint.

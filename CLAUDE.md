# CLAUDE.md – DSS-IN-MCP

Invoice-Ninja-MCP (FastMCP 3.4.7, Streamable HTTP `/mcp`, Port 8539). Seit 23.09.2026 eigenes Repo,
vorher Teil von DSS-PMS (`mcp_server.py`, `services/in_mcp_tools.py`, bis Commit ea2d020).

- Paket `in_mcp/`: `server.py` (Registrierung, Token, Fehler), `tools.py` (Logik, liest `K`),
  `ninja.py` (IN-HTTP), `angebot.py` (Helfer), `konfig.py` (instanz.yaml), `pms.py` (optional),
  `protokoll.py` (Logger)
- **Instanzen:** Derselbe Code läuft an jedem Standort; instanzspezifisch sind ausschließlich `.env`
  (Zugangsdaten, Tokens, optionale `PMS_DB_PATH`/`LOG_DATEI`) und `instanz.yaml` (Custom-Field-Rollen,
  Angebotsregeln). Lokale Deploy-Details (Container-Name, Netze, Volumes) gehören in
  `docker-compose.override.yml` (gitignored, nicht Teil des Repos) — Vorlage siehe `beispiele/`.
  Betriebsdetails der DSS-eigenen Instanz: Vault-Artikel `concepts/dss-in-mcp`
- **Tests:** `scripts/test.sh`; Standard-Konfiguration in `tests/conftest.py` nutzt `beispiele/instanz.dss.yaml`
  (Referenzinstanz mit vollem Rollen-Set), neutrales Verhalten in `tests/test_neutral.py`
- Beschriftungen der Custom Fields werden 5 Minuten gecacht (`LABEL_CACHE_SEKUNDEN` in
  `in_mcp/tools.py`). Der FastMCP-Servername `dss-invoice-ninja` (`in_mcp/server.py`) ist bewusst
  fest verdrahtet, nicht pro Kunde konfigurierbar: Kunden sehen ihn in ihrem MCP-Client, und die
  Instanzbezeichnung steht ohnehin in den Server-Instructions
- **Deploy:** `docker compose up -d --build` im Repo-Ordner. MCP-Clients übernehmen neue Tools/Felder
  meist erst nach einem eigenen Neustart, manche cachen `.env` beim eigenen Start
- IN-Gotchas (gelten für jedes IN): Client-PUT ersetzt die Kontaktliste, MwSt. je Position,
  `tax_id` = Steuerkategorie, Schreibaufrufe mit `Accept: application/json`, `status_id` ist ein String
- Spec und Plan liegen in DSS-PMS: `docs/superpowers/specs/2026-09-23-in-mcp-eigenes-repo-design.md`,
  `docs/superpowers/plans/2026-09-23-in-mcp-eigenes-repo.md`

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
- **Tool-Zahl:** `LESE_TOOLS` 14 (ohne `PMS_DB_PATH` 13), `SCHREIB_TOOLS` 7, `RECHNUNGS_TOOLS` 8
  (`schreiben` 4, `status` 2, `versenden` 1, `stornieren` 1). Also 20 bis 29, DSS-Referenz 29.
  README (DE + EN) nennt die Zahlen; bei neuen Tools dort und in `anweisungen()` nachziehen.
  `destructiveHint: false` für `NICHT_DESTRUKTIV` in `server.py`: Entwürfe anlegen/ändern
  (Angebot, Rechnung, deren Positionen/Kopf), Umwandeln, `notiz_setzen` - kein Effekt nach außen,
  umkehrbar, keine Stammdaten. `true` bleibt für Versand, Zahlung, Storno, Stammdaten (Kunde,
  Kontakt, Produkt) - Claude Desktop fragt bei `true` bei jedem Aufruf erneut nach, auch nach
  "Always allow", darum die Trennung (Entscheidung 24.09.2026)
- **Rechte-Block `rechnungen:`** in instanz.yaml (`schreiben`, `status`, `versenden`,
  `stornieren`, Default alle `false`, nur bool). `baue_mcp()` registriert ein Rechnungs-Tool nur mit
  `k.rechnungen_erlaubt(recht)`, Zuordnung in `RECHNUNGS_TOOLS`. `anweisungen()` nennt die
  freigeschalteten Rechte
- **Verkaufsbedingungen (VKB), Regeln 1-5** in `tools.py` (`_vkb_keys`, `_positionen_bauen`,
  `_vkb_setzen`), nur für die Angebots-Tools: 1) erkannt werden `angebot.verkaufsbedingungen` plus
  Katalog-Keys passend zu `verkaufsbedingungen_muster` (`re.search`, case-sensitiv), Positionen
  case-insensitiv zugeordnet; 2) VKB in `positionen` gewinnt (eigener Text bleibt, ans Ende, `fest`),
  Parameter-Widerspruch nur als Hinweis; 3) Parameter = erkannter Key oder `keine`, leer = bisherige
  (letzte) bzw. Standard; 4) mehr als eine VKB in `positionen` = Fehler ohne Schreibaufruf;
  5) Rückmeldung nennt VKB und Herkunft. Weder Liste noch Muster: Argument ausgeblendet, keine Logik.
  Rechnungen: VKB ist eine normale Position, nichts wird angehängt
- **Rechnungen und GoBD:** Nummer wird beim Anlegen/Umwandeln vergeben, deshalb nie löschen,
  falsche Rechnung stornieren. Ändern nur bei Status 1 und nicht archiviert
  (`_rechnungsentwurf_pruefen`), auch wenn IN mehr erlaubt. Vor jeder Änderung frisch lesen
  (`_rechnung_frisch`). Storno setzt nur Status 5, keine Gutschrift. Versand geht in die
  IN-Mailwarteschlange (Antwort = angenommen, nicht zugestellt), IN wählt die Vorlage. Umwandeln
  gesperrt nur bei `invoice_id` gesetzt oder Status -1. Nur Als-versendet-Markieren und Storno prüfen
  den Status danach erneut. Live-Tests nur lesend, weil jede angelegte Rechnung eine Nummer verbraucht
- Optionale Positionen: IN 5.13 hat kein Feld dafür, nicht umsetzbar
- Spec und Plan liegen in DSS-PMS: `docs/superpowers/specs/2026-09-23-in-mcp-eigenes-repo-design.md`,
  `docs/superpowers/plans/2026-09-23-in-mcp-eigenes-repo.md`
- **Öffentliche Fassung:** `github.com/DSS-AI/invoice-ninja-mcp` (MIT, eigene Historie). Übertrag nur mit
  `scripts/veroeffentlichen.sh` (prüft auf interne Angaben, fragt vor dem Push; das Skript ist nur im
  Arbeits-Repo vorhanden). Nie die Historie dieses Repos ins öffentliche pushen
  **Nie direkt im öffentlichen Repo committen:** `veroeffentlichen.sh` ersetzt den öffentlichen Stand
  vollständig und löscht solche Änderungen. Ist es doch passiert, zuerst ins private Repo zurückholen
  (Fall 24.09.2026: Hermes-Abschnitt, zurückgeholt am 28.10.2026 mit `eac04c1`)

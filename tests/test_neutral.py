"""Verhalten ohne Rollen (instanz.neutral.yaml): nichts DSS-Spezifisches darf greifen."""
import copy
from datetime import date
from unittest.mock import MagicMock

import pytest

from in_mcp import tools as t

HEUTE = date(2026, 9, 23)

KUNDE = {
    "id": "c1", "number": "1001", "name": "Kunde GmbH", "city": "Köln",
    "custom_value1": "Kostenstelle 4711", "custom_value2": "", "custom_value3": "", "custom_value4": "",
    "contacts": [{"id": "k1", "first_name": "Eva", "last_name": "Test", "email": "eva@kunde.de",
                  "phone": "", "custom_value1": "Einkauf", "custom_value4": ""}],
}


@pytest.fixture
def neutral_mock(neutral, monkeypatch):
    stand = {"clients": [copy.deepcopy(KUNDE)], "quotes": [], "projects": [], "invoices": [],
             "aufrufe": [], "log": []}
    monkeypatch.setattr(t.nn, "get_all_clients", lambda: copy.deepcopy(stand["clients"]))
    monkeypatch.setattr(t.nn, "get_client",
                        lambda cid: copy.deepcopy(next(c for c in stand["clients"] if c["id"] == cid)))
    monkeypatch.setattr(t.nn, "get_quotes_listing", lambda: copy.deepcopy(stand["quotes"]))
    monkeypatch.setattr(t.nn, "get_projects_listing", lambda: copy.deepcopy(stand["projects"]))
    monkeypatch.setattr(t.nn, "get_invoices_listing", lambda: copy.deepcopy(stand["invoices"]))
    monkeypatch.setattr(t.nn, "get_custom_field_labels", lambda: {
        "client1": "Kostenstelle", "contact1": "Bereich", "invoice1": "Vorgang", "project1": "Auftrag"})

    def update_contacts(cid, contacts):
        stand["aufrufe"].append(("contacts", cid, copy.deepcopy(contacts)))
        return {"id": cid, "contacts": [dict(c, id=c.get("id") or f"neu{i}") for i, c in enumerate(contacts)]}

    monkeypatch.setattr(t.nn, "update_client_contacts", update_contacts)
    monkeypatch.setattr(t, "log", MagicMock())
    return stand


# --- Kunde und Kontakt -----------------------------------------------------------

def test_kunde_ohne_mandant_rolle(neutral_mock):
    assert t.kunden_suchen("4711")["treffer"] == []          # custom_value1 ist kein Suchfeld
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.kunde_lesen("Kostenstelle 4711")                    # und kein Kundenschlüssel
    k = t.kunde_lesen("1001")
    assert "mandant_nr" not in k


def test_kontakt_ohne_anrede_und_zusatzrollen(neutral_mock):
    kontakt = t.kunde_lesen("1001")["kontakte"][0]
    assert "anrede" not in kontakt
    assert not {"mobil", "position", "abteilung"} & set(kontakt)
    assert kontakt["vorname"] == "Eva" and kontakt["telefon"] == ""


def test_kontakt_speichern_ohne_anrede(neutral_mock):
    text = t.kontakt_speichern("desktop", "1001", "Max", "Neu", "max@kunde.de")
    assert text == "Kontakt Max Neu bei Kunde GmbH angelegt."
    neu = neutral_mock["aufrufe"][-1][2][-1]
    assert "custom_value4" not in neu
    assert neu["first_name"] == "Max" and neu["email"] == "max@kunde.de"


def test_kontakt_aendern_laesst_custom_values_unangetastet(neutral_mock):
    t.kontakt_speichern("desktop", "1001", "Eva", "Test", "eva@kunde.de", kontakt_id="k1", telefon="0221 1")
    geaendert = neutral_mock["aufrufe"][-1][2][0]
    assert geaendert["phone"] == "0221 1"
    assert geaendert["custom_value1"] == "Einkauf" and geaendert["custom_value4"] == ""


# --- Angebot, Rechnung, Projekt, Notiz --------------------------------------------

def _quote(nr="AN-1", status="1", **extra):
    q = {"id": f"q{nr}", "number": nr, "status_id": status, "custom_value1": "V-7", "custom_value2": "",
         "custom_value3": "yes", "custom_value4": "yes", "date": "2026-09-01", "due_date": "2026-09-30",
         "amount": 119.0, "total_taxes": 19.0, "po_number": "", "private_notes": "", "public_notes": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Kunde GmbH", "number": "1001"},
         "line_items": []}
    q.update(extra)
    return q


def _projekt(**extra):
    p = {"id": "p1", "number": "0007", "name": "Umbau Halle 3 (AG1260001)", "custom_value1": "A-1",
         "custom_value2": "", "custom_value3": "yes", "custom_value4": "", "private_notes": "alt",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Kunde GmbH", "number": "1001"}}
    p.update(extra)
    return p


def test_angebot_ohne_rollen(neutral_mock):
    neutral_mock["quotes"] = [_quote()]
    a = t.angebot_lesen("AN-1")
    assert not {"bezeichnung", "projektnummer", "bestellt", "abgeschlossen"} & set(a)
    assert a["status"] == "Entwurf" and a["netto"] == 100.0


def test_projekt_ohne_rollen(neutral_mock):
    neutral_mock["projects"] = [_projekt()]
    p = t.projekt_lesen("0007")                       # IN-Nummer
    assert p["projektname"] == "Umbau Halle 3 (AG1260001)"
    assert not {"projektnummer", "abgeschlossen", "notiz", "angebotsnr"} & set(p)
    assert p["angebot"] is None
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.projekt_lesen("A-1")                        # custom_value1 ist keine Projektnummer
    assert [x["in_nummer"] for x in t.projekte_suchen()["treffer"]] == ["0007"]


def test_projekt_rechnungen_ohne_rollen_nur_project_id(neutral_mock):
    neutral_mock["projects"] = [_projekt()]
    neutral_mock["invoices"] = [
        {"number": "R-1", "date": "2026-09-01", "amount": 100, "status_id": "2", "project_id": "p1"},
        {"number": "R-2", "date": "2026-09-02", "amount": 200, "status_id": "2", "project_id": "",
         "custom_value1": "A-1"},                     # ohne Rolle ist custom_value1 keine Projektnummer
    ]
    assert [r["rechnungsnr"] for r in t.projekt_lesen("0007")["rechnungen"]] == ["R-1"]

def test_rechnung_ohne_rollen(neutral_mock):
    neutral_mock["invoices"] = [{"id": "i1", "number": "R-1", "status_id": "2", "date": "2026-09-01",
                                 "amount": 119.0, "total_taxes": 19.0, "balance": 119.0, "custom_value1": "V-7",
                                 "is_deleted": False, "client": {"name": "Kunde GmbH", "number": "1001"}}]
    r = t.rechnungen_suchen()["treffer"][0]
    assert "projektnummer" not in r and "projektbezeichnung" not in r


def test_rohdaten_ohne_rollen(neutral_mock, monkeypatch):
    monkeypatch.setattr(t.nn, "get_listing", lambda pfad, **p: copy.deepcopy(
        neutral_mock["clients"] if pfad == "clients" else [_projekt()] if pfad == "projects" else []))
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.in_rohdaten("kunde", "Kostenstelle 4711")
    assert t.in_rohdaten("projekt", "0007")["daten"]["id"] == "p1"


def test_notiz_ohne_rolle_geht_in_private_notes(neutral_mock, monkeypatch):
    neutral_mock["projects"] = [_projekt()]
    monkeypatch.setattr(t.nn, "update_project",
                        lambda pid, felder: neutral_mock["aufrufe"].append(("project", pid, felder)) or True)
    text = t.notiz_setzen("desktop", "0007", "Termin 2.10.", heute=HEUTE)
    assert neutral_mock["aufrufe"][-1] == ("project", "p1", {"private_notes": "alt\n23.09.2026: Termin 2.10."})
    assert text == "Notiz an Projekt 0007 (private Notiz) angehängt."


def test_notiz_findet_angebot_ohne_praefix(neutral_mock, monkeypatch):
    neutral_mock["quotes"] = [_quote()]
    monkeypatch.setattr(t.nn, "update_quote_private_notes",
                        lambda qid, text: neutral_mock["aufrufe"].append(("quote_notes", qid, text)) or True)
    t.notiz_setzen("desktop", "AN-1", "Rückruf", heute=HEUTE)
    assert neutral_mock["aufrufe"][-1] == ("quote_notes", "qAN-1", "23.09.2026: Rückruf")


def test_notiz_ziel_unbekannt(neutral_mock):
    with pytest.raises(t.ToolFehler, match="Weder Angebot noch Projekt XY gefunden"):
        t.notiz_setzen("desktop", "XY", "x", heute=HEUTE)


def test_notiz_ziel_mehrdeutig_angebot_und_projekt_gleiche_nummer(neutral_mock, monkeypatch):
    neutral_mock["quotes"] = [_quote(nr="0007")]
    neutral_mock["projects"] = [_projekt()]
    monkeypatch.setattr(t.nn, "update_quote_private_notes",
                        lambda qid, text: neutral_mock["aufrufe"].append(("quote_notes", qid, text)) or True)
    monkeypatch.setattr(t.nn, "update_project",
                        lambda pid, felder: neutral_mock["aufrufe"].append(("project", pid, felder)) or True)
    with pytest.raises(t.ToolFehler, match="0007 ist sowohl Angebot als auch Projekt"):
        t.notiz_setzen("desktop", "0007", "x", heute=HEUTE)
    assert neutral_mock["aufrufe"] == []


def test_notiz_ueber_projekt_in_id_trotz_gleicher_angebotsnummer(neutral_mock, monkeypatch):
    neutral_mock["quotes"] = [_quote(nr="0007")]
    neutral_mock["projects"] = [_projekt()]
    monkeypatch.setattr(t.nn, "update_project",
                        lambda pid, felder: neutral_mock["aufrufe"].append(("project", pid, felder)) or True)
    text = t.notiz_setzen("desktop", "p1", "Termin 2.10.", heute=HEUTE)
    assert neutral_mock["aufrufe"][-1] == ("project", "p1", {"private_notes": "alt\n23.09.2026: Termin 2.10."})
    assert text == "Notiz an Projekt 0007 (private Notiz) angehängt."


# --- Angebotsregeln ----------------------------------------------------------------

@pytest.fixture
def katalog(neutral_mock, monkeypatch):
    monkeypatch.setattr(t.nn, "get_products", lambda: [
        {"id": "p1", "product_key": "Beratung", "notes": "Beratung je Stunde", "price": 100.0,
         "tax_name1": "MwSt.", "tax_rate1": 19, "tax_id": "2"}])
    monkeypatch.setattr(t.nn, "create_quote", lambda payload: neutral_mock["aufrufe"].append(("quote", payload))
                        or {"id": "qneu", "number": "AN-9"})
    monkeypatch.setattr(t.nn, "update_quote_line_items",
                        lambda qid, items: neutral_mock["aufrufe"].append(("line_items", qid, items)) or {"id": qid})
    monkeypatch.setattr(t.nn, "update_quote",
                        lambda qid, felder: neutral_mock["aufrufe"].append(("quote_update", qid, felder))
                        or {"id": qid, **felder})
    monkeypatch.setattr(t.nn, "create_product", lambda payload: neutral_mock["aufrufe"].append(
        ("product_create", payload)) or {"id": "pneu"})
    monkeypatch.setattr(t.nn, "get_tax_rates", lambda: [{"id": "x", "name": "MwSt.", "rate": 19.0}])
    monkeypatch.setattr(t, "log_angebot", lambda nr, qid, cid: neutral_mock["log"].append(nr))
    return neutral_mock


def test_entwurf_ohne_vkb_ohne_bezeichnung(katalog):
    text = t.angebotsentwurf_anlegen("desktop", "1001", ["eva@kunde.de"], [{"produkt": "Beratung", "menge": 2}],
                                     heute=HEUTE)
    _, payload = katalog["aufrufe"][-1]
    assert [i["product_key"] for i in payload["line_items"]] == ["Beratung"]
    assert not any(k.startswith("custom_value") for k in payload)
    assert payload["due_date"] == "2026-10-23"          # Standard 30 Tage
    assert "200.00 € netto" in text


def test_entwurf_gueltigkeit_nach_konfiguration(katalog):
    with pytest.raises(t.ToolFehler, match="höchstens 365 Tage"):
        t.angebotsentwurf_anlegen("desktop", "1001", ["eva@kunde.de"], [{"produkt": "Beratung"}],
                                  gueltig_bis="2027-12-31", heute=HEUTE)
    t.angebotsentwurf_anlegen("desktop", "1001", ["eva@kunde.de"], [{"produkt": "Beratung"}],
                              gueltig_bis="2026-09-24", heute=HEUTE)   # 1 Tag ist erlaubt


def test_entwurf_vkb_ohne_konfiguration_abgelehnt(katalog):
    with pytest.raises(t.ToolFehler, match="keine Verkaufsbedingungen"):
        t.angebotsentwurf_anlegen("desktop", "1001", ["eva@kunde.de"], [{"produkt": "Beratung"}],
                                  verkaufsbedingungen="VKBMA", heute=HEUTE)


def test_positionen_setzen_ohne_bestell_sperre(katalog):
    katalog["quotes"] = [_quote()]           # custom_value3/4 = "yes", ohne Rolle bedeutungslos
    text = t.angebotsentwurf_positionen_setzen("desktop", "AN-1", [{"produkt": "Beratung"}])
    assert [i["product_key"] for i in katalog["aufrufe"][-1][2]] == ["Beratung"]
    assert "Verkaufsbedingungen" not in text
    katalog["quotes"] = [_quote(status="2")]
    with pytest.raises(t.ToolFehler, match="nicht Entwurf"):
        t.angebotsentwurf_positionen_setzen("desktop", "AN-1", [{"produkt": "Beratung"}])


def test_kopf_setzen_ohne_bezeichnungsrolle(katalog):
    """Ohne Rolle angebot.bezeichnung funktionieren gueltig_bis/oeffentliche_notiz weiterhin,
    bezeichnung wird explizit abgelehnt statt einfach ignoriert."""
    katalog["quotes"] = [_quote()]
    text = t.angebotsentwurf_kopf_setzen("desktop", "AN-1", oeffentliche_notiz="Hinweis", heute=HEUTE)
    (_, _, felder), = [a for a in katalog["aufrufe"] if a[0] == "quote_update"]
    assert felder == {"public_notes": "Hinweis"}
    assert "AN-1" in text
    with pytest.raises(t.ToolFehler, match="Diese Instanz kennt keine Bezeichnung"):
        t.angebotsentwurf_kopf_setzen("desktop", "AN-1", bezeichnung="Neu")


def test_produkt_neu_mit_konfigurierter_steuerkategorie(katalog, monkeypatch):
    monkeypatch.setattr(t, "K", t.K.__class__(neue_steuerkategorie="1"))
    t.produkt_speichern("desktop", "Ware", text="Ware", preis=5, mwst="19")
    assert katalog["aufrufe"][-1][1]["tax_id"] == "1"


# --- Zusatzfelder -------------------------------------------------------------------

def test_zusatzfelder_mit_in_beschriftung(neutral_mock):
    k = t.kunde_lesen("1001")
    assert k["zusatzfelder"] == {"Kostenstelle": "Kostenstelle 4711"}
    assert k["kontakte"][0]["zusatzfelder"] == {"Bereich": "Einkauf"}
    neutral_mock["quotes"] = [_quote()]
    assert t.angebot_lesen("AN-1")["zusatzfelder"] == {"Vorgang": "V-7", "custom_value3": "yes",
                                                        "custom_value4": "yes"}
    neutral_mock["projects"] = [_projekt()]
    assert t.projekt_lesen("0007")["zusatzfelder"] == {"Auftrag": "A-1", "custom_value3": "yes"}


def test_zusatzfelder_fehlen_wenn_alles_leer(neutral_mock):
    neutral_mock["clients"][0]["custom_value1"] = ""
    assert "zusatzfelder" not in t.kunden_suchen("Kunde")["treffer"][0]


def test_beschriftungen_werden_gecacht(neutral_mock, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(t.nn, "get_custom_field_labels", lambda: aufrufe.append(1) or {"client1": "KSt"})
    t.kunde_lesen("1001")
    t.kunde_lesen("1001")
    assert len(aufrufe) == 1


def test_beschriftungen_nicht_lesbar_faellt_auf_feldnamen_zurueck(neutral_mock, monkeypatch):
    def kaputt():
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(t.nn, "get_custom_field_labels", kaputt)
    k = t.kunde_lesen("1001")
    assert k["zusatzfelder"] == {"custom_value1": "Kostenstelle 4711"}
    assert t.log.warning.called


# --- Server ---------------------------------------------------------------------------

def test_neutral_blendet_argumente_ohne_rolle_aus(neutral, monkeypatch):
    import asyncio
    from in_mcp import server
    monkeypatch.delenv("PMS_DB_PATH", raising=False)
    tools = {tool.name: tool for tool in asyncio.run(server.baue_mcp(t.K).list_tools())}
    assert "angebot_vorlagen_auflisten" not in tools
    assert set(tools["kontakt_speichern"].parameters["properties"]) == \
        {"kunde", "vorname", "nachname", "email", "telefon", "kontakt_id", "email_aendern"}
    assert "bestellt" not in tools["angebote_suchen"].parameters["properties"]
    assert "abgeschlossen" not in tools["projekte_suchen"].parameters["properties"]
    assert not {"bezeichnung", "verkaufsbedingungen"} & set(tools["angebotsentwurf_anlegen"].parameters["properties"])
    assert "verkaufsbedingungen" not in tools["angebotsentwurf_positionen_setzen"].parameters["properties"]
    assert "bezeichnung" not in tools["angebotsentwurf_kopf_setzen"].parameters["properties"]
    assert {"gueltig_bis", "oeffentliche_notiz"} <= set(tools["angebotsentwurf_kopf_setzen"].parameters["properties"])
    for tool in tools.values():                     # keine DSS-Begriffe in den Beschreibungen
        assert not any(w in tool.description for w in ("AG…", "P…", "RG…", "VKBMA", "Termin", "PMS"))


def test_neutral_ausgeblendete_argumente_greifen_nicht(neutral_mock, monkeypatch):
    import asyncio
    from fastmcp import Client
    from in_mcp import server
    monkeypatch.setattr(server, "log", MagicMock())
    mcp = server.baue_mcp(t.K)

    async def aufruf():
        async with Client(mcp) as c:
            return await c.call_tool("kunden_suchen", {"text": "Kunde"})

    assert asyncio.run(aufruf()).data["anzahl"] == 1


def test_nur_muster_zeigt_verkaufsbedingungen(neutral, monkeypatch):
    """Ohne Liste, aber mit Muster kennt die Instanz Verkaufsbedingungen: Argument sichtbar."""
    import dataclasses
    from in_mcp import server
    k = dataclasses.replace(t.K, verkaufsbedingungen_muster="^AGB")
    assert "verkaufsbedingungen" not in server.versteckte_argumente(k).get("angebotsentwurf_anlegen", [])
    assert "angebotsentwurf_positionen_setzen" not in server.versteckte_argumente(k)
    assert "'^AGB'" in server.anweisungen(k)


def test_anweisungen_neutral(neutral):
    from in_mcp import server
    text = server.anweisungen(t.K)
    assert text.startswith("Zugriff auf das Invoice Ninja von Beispiel GmbH")
    assert "Verkaufsbedingungen" not in text and "Anrede" not in text and "1 bis 365 Tage" in text

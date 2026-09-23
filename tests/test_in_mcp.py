"""Tests für den Invoice-Ninja-MCP (services/in_mcp_tools.py, mcp_server.py)."""
import copy
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from in_mcp import tools as t

REPO = Path(__file__).resolve().parents[1]
BEISPIELE = REPO / "beispiele"

HEUTE = date(2026, 9, 23)

KUNDE = {
    "id": "c1", "number": "70001", "name": "Muster GmbH", "city": "Darmstadt", "custom_value1": "",
    "address1": "Weg 1", "postal_code": "64283", "vat_number": "DE123", "private_notes": "",
    "contacts": [{"id": "k1", "first_name": "Anna", "last_name": "Alt", "email": "anna@muster.de",
                  "phone": "", "custom_value4": "Frau"}],
}
ANDERER = {"id": "c2", "number": "70002", "name": "Beispiel AG", "city": "Mainz", "custom_value1": "",
           "contacts": []}


def _quote(nr, status="2", bestellt="", datum="2026-09-01", kunde=KUNDE, bez="RB Presse", **extra):
    q = {"id": f"q{nr}", "number": nr, "status_id": status, "custom_value3": bestellt, "custom_value4": "",
         "custom_value1": "", "custom_value2": bez, "date": datum, "due_date": "2026-09-30",
         "amount": 1190.0, "total_taxes": 190.0, "po_number": "", "private_notes": "", "public_notes": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": kunde["name"], "number": kunde["number"]},
         "line_items": [{"product_key": "RB-MAVO", "notes": "RB", "quantity": 1, "cost": 1000, "tax_rate1": 19}]}
    q.update(extra)
    return q


def _invoice(nr, status="2", datum="2026-09-01", kunde=KUNDE, balance=500.0, amount=1190.0, **extra):
    i = {"id": f"i{nr}", "number": nr, "status_id": status, "date": datum, "due_date": "2026-10-01",
         "amount": amount, "total_taxes": 190.0, "balance": balance, "po_number": "", "custom_value1": "",
         "custom_value2": "", "paid_to_date": 0, "private_notes": "", "discount": 0,
         "is_amount_discount": False, "is_deleted": False,
         "client": {"name": kunde["name"], "number": kunde["number"]},
         "line_items": [{"product_key": "RB-MAVO", "notes": "RB", "quantity": 1, "cost": 1000, "tax_rate1": 19}]}
    i.update(extra)
    return i


@pytest.fixture
def in_mock(monkeypatch):
    """Invoice Ninja im Speicher. Schreibaufrufe landen in `aufrufe`."""
    stand = {"clients": [copy.deepcopy(KUNDE), copy.deepcopy(ANDERER)], "quotes": [], "projects": [],
             "invoices": [], "payments": [], "vendors": [], "products": [], "documents": [], "aufrufe": [],
             "log": []}
    # Rohdaten-Pfade (in_rohdaten) laufen über get_listing; Alias auf dieselben Listen wie oben
    _pfad_zu_stand = {"clients": "clients", "quotes": "quotes", "projects": "projects",
                      "invoices": "invoices", "products": "products", "payments": "payments",
                      "vendors": "vendors"}
    monkeypatch.setattr(t.nn, "get_all_clients", lambda: copy.deepcopy(stand["clients"]))
    monkeypatch.setattr(t.nn, "get_client",
                        lambda cid: copy.deepcopy(next(c for c in stand["clients"] if c["id"] == cid)))
    monkeypatch.setattr(t.nn, "get_quotes_listing", lambda: copy.deepcopy(stand["quotes"]))
    monkeypatch.setattr(t.nn, "get_projects_listing", lambda: copy.deepcopy(stand["projects"]))
    monkeypatch.setattr(t.nn, "get_invoices_listing", lambda: copy.deepcopy(stand["invoices"]))
    monkeypatch.setattr(t.nn, "get_invoices_for_project", lambda pid: [])
    monkeypatch.setattr(t.nn, "get_payments_listing", lambda: copy.deepcopy(stand["payments"]))
    monkeypatch.setattr(t.nn, "get_vendors_listing", lambda: copy.deepcopy(stand["vendors"]))
    monkeypatch.setattr(t.nn, "get_entity_documents", lambda pfad, eid: copy.deepcopy(stand["documents"]))
    monkeypatch.setattr(t.nn, "get_listing",
                        lambda pfad, **p: copy.deepcopy(stand.get(_pfad_zu_stand.get(pfad, ""), [])))
    monkeypatch.setattr(t.nn, "get_custom_field_labels", lambda: {
        "client1": "Mandant-Nr.", "client2": "Sonstiges", "contact1": "Mobil",
        "invoice1": "Projektnummer", "project1": "Projektnummer", "vendor1": "Lieferantenart"})
    return stand


def test_aufrufer_fuer():
    tokens = {"desktop": "abc", "hermes": "xyz", "leer": ""}
    assert t.aufrufer_fuer("Bearer abc", tokens) == "desktop"
    assert t.aufrufer_fuer("Bearer xyz", tokens) == "hermes"
    assert t.aufrufer_fuer("Bearer falsch", tokens) is None
    assert t.aufrufer_fuer("abc", tokens) is None
    assert t.aufrufer_fuer("Bearer ", tokens) is None  # leeres Token passt nie auf eine leere Variable
    assert t.aufrufer_fuer("", tokens) is None


def test_aufrufer_fuer_nicht_ascii_ergibt_none_statt_fehler():
    tokens = {"desktop": "abc"}
    assert t.aufrufer_fuer("Bearer äöü", tokens) is None


def test_kunden_suchen_nach_name_nummer_email(in_mock):
    assert [c["kundennummer"] for c in t.kunden_suchen("muster")["treffer"]] == ["70001"]
    assert [c["kundennummer"] for c in t.kunden_suchen("70002")["treffer"]] == ["70002"]
    assert [c["kundennummer"] for c in t.kunden_suchen("anna@")["treffer"]] == ["70001"]
    assert t.kunden_suchen("")["anzahl"] == 0


def test_suche_kappt_bei_50(in_mock):
    in_mock["clients"] = [dict(ANDERER, id=f"c{i}", number=str(i), name=f"Firma {i:03}") for i in range(60)]
    erg = t.kunden_suchen("firma")
    assert len(erg["treffer"]) == 50 and erg["anzahl"] == 60 and "eingrenzen" in erg["hinweis"]


def test_kunde_lesen_mit_kontakten(in_mock):
    k = t.kunde_lesen("70001")
    assert k["name"] == "Muster GmbH" and k["kontakte"][0]["anrede"] == "Frau"
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.kunde_lesen("99999")


def test_kunde_lesen_erweiterte_felder(in_mock):
    in_mock["clients"][0].update(
        custom_value1="F1", state="Hessen", shipping_address1="Lager 1", shipping_address2="Halle 2",
        shipping_postal_code="64289", shipping_city="Darmstadt", shipping_state="Hessen",
        paid_to_date=500.5, balance=120.25, payment_balance=30, credit_balance=75.5)
    k = t.kunde_lesen("70001")
    assert k["mandant_nr"] == "F1" and k["bundesland"] == "Hessen"
    assert k["lieferadresse"] == {"strasse": "Lager 1", "zusatz": "Halle 2", "plz": "64289",
                                  "ort": "Darmstadt", "bundesland": "Hessen"}
    assert (k["umsatz_bezahlt"], k["saldo_offen"]) == (500.5, 120.25)
    # payment_balance = nicht zugeordnete Zahlungen (Anzahlungen ohne Rechnung), credit_balance =
    # Gutschrift-Guthaben - zwei unterschiedliche IN-Felder, vorher fälschlich beide als "guthaben" (Task 5)
    assert (k["nicht_zugeordnete_zahlungen"], k["gutschrift_guthaben"]) == (30.0, 75.5)


def test_kunde_lesen_ohne_lieferadresse(in_mock):
    assert t.kunde_lesen("70001")["lieferadresse"] is None


def test_kunden_suchen_mandant_nr(in_mock):
    in_mock["clients"][0]["custom_value1"] = "F1"
    assert t.kunden_suchen("muster")["treffer"][0]["mandant_nr"] == "F1"


def test_angebote_suchen_filter_und_netto(in_mock):
    in_mock["quotes"] = [
        _quote("AG1260001", status="2", datum="2026-08-01"),
        _quote("AG1260002", status="3", bestellt="yes", datum="2026-09-10"),
        _quote("AG1260003", status="-1", kunde=ANDERER, datum="2026-09-15"),
        _quote("AG1260004", is_deleted=True),
    ]
    alle = t.angebote_suchen()["treffer"]
    assert [q["angebotsnr"] for q in alle] == ["AG1260003", "AG1260002", "AG1260001"]  # neueste zuerst, ohne gelöschte
    assert alle[0]["netto"] == 1000.0 and alle[0]["status"] == "abgelaufen"
    assert [q["angebotsnr"] for q in t.angebote_suchen(bestellt=True)["treffer"]] == ["AG1260002"]
    assert [q["angebotsnr"] for q in t.angebote_suchen(kunde="70002")["treffer"]] == ["AG1260003"]
    assert [q["angebotsnr"] for q in t.angebote_suchen(status="Versendet")["treffer"]] == ["AG1260001"]
    assert [q["angebotsnr"] for q in t.angebote_suchen(von="2026-09-01", bis="2026-09-12")["treffer"]] == ["AG1260002"]


def test_angebot_lesen_mit_positionen(in_mock):
    in_mock["quotes"] = [_quote("AG1260001")]
    q = t.angebot_lesen("ag1260001")
    assert q["angebotsnr"] == "AG1260001" and q["positionen"][0]["produkt"] == "RB-MAVO"
    with pytest.raises(t.ToolFehler, match="AG1269999 nicht gefunden"):
        t.angebot_lesen("AG1269999")


def test_angebot_kurz_rabatt_und_steuer(in_mock):
    in_mock["quotes"] = [
        _quote("AG1260001", discount=10, is_amount_discount=False, tax_name1="MwSt.", tax_rate1=19),
        _quote("AG1260002", discount=50, is_amount_discount=True),
        _quote("AG1260003", discount=0),
    ]
    treffer = {a["angebotsnr"]: a for a in t.angebote_suchen()["treffer"]}
    assert treffer["AG1260001"]["rabatt"] == "10 %"
    assert treffer["AG1260001"]["steuer_kopf"] == "MwSt. 19 %"
    assert treffer["AG1260002"]["rabatt"] == "50.00 €"
    assert treffer["AG1260003"]["rabatt"] == "" and treffer["AG1260003"]["steuer_kopf"] == ""


def test_angebot_kurz_steuer_kopf_ohne_nachkommastellen(in_mock):
    """tax_rate1 kommt aus IN teils als float (19.0) - steuer_kopf muss trotzdem "19 %" zeigen (Task 8)."""
    in_mock["quotes"] = [_quote("AG1260001", tax_name1="MwSt.", tax_rate1=19.0)]
    treffer = t.angebote_suchen()["treffer"][0]
    assert treffer["steuer_kopf"] == "MwSt. 19 %"


def test_angebot_kurz_in_rechnung_umgewandelt(in_mock):
    in_mock["quotes"] = [_quote("AG1260001", invoice_id="i1"), _quote("AG1260002")]
    treffer = {a["angebotsnr"]: a for a in t.angebote_suchen()["treffer"]}
    assert treffer["AG1260001"]["in_rechnung_umgewandelt"] is True
    assert treffer["AG1260002"]["in_rechnung_umgewandelt"] is False


def test_angebot_lesen_rechnungsnr(in_mock):
    in_mock["quotes"] = [_quote("AG1260001", invoice_id="i1")]
    in_mock["invoices"] = [{"id": "i1", "number": "RG1260005"}]
    assert t.angebot_lesen("AG1260001")["rechnungsnr"] == "RG1260005"
    in_mock["quotes"] = [_quote("AG1260002")]
    assert t.angebot_lesen("AG1260002")["rechnungsnr"] == ""


def test_angebot_lesen_positionen_erweitert(in_mock):
    in_mock["quotes"] = [_quote("AG1260001", line_items=[
        {"product_key": "RB-MAVO", "notes": "RB", "quantity": 1, "cost": 1000, "tax_rate1": 19,
         "line_total": 1000.0, "gross_line_total": 1190.0, "tax_amount": 190.0, "tax_name1": "MwSt."},
        {"product_key": "VKBMA", "notes": "", "quantity": 1, "cost": 0},
    ])]
    pos = t.angebot_lesen("AG1260001")["positionen"]
    assert pos[0]["netto"] == 1000.0 and pos[0]["brutto"] == 1190.0
    assert pos[0]["steuerbetrag"] == 190.0 and pos[0]["steuer"] == "MwSt."
    assert pos[1]["netto"] == 0 and pos[1]["steuer"] == ""


def test_projekte_suchen_und_lesen(in_mock):
    in_mock["projects"] = [
        {"id": "p1", "name": "Angebot # AG1260001 [Muster GmbH]", "custom_value1": "P260010",
         "custom_value2": "RB Presse", "custom_value3": "", "custom_value4": "Termin 1.10.",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"}},
        {"id": "p2", "name": "Angebot # AG1260002 [Beispiel AG]", "custom_value1": "P260011",
         "custom_value2": "BA", "custom_value3": "yes", "custom_value4": "",
         "archived_at": 1, "is_deleted": False, "client": {"name": "Beispiel AG", "number": "70002"}},
    ]
    in_mock["quotes"] = [_quote("AG1260001")]
    assert [p["projektnummer"] for p in t.projekte_suchen(abgeschlossen=False)["treffer"]] == ["P260010"]
    p = t.projekt_lesen("P260010")
    assert p["angebotsnr"] == "AG1260001" and p["notiz"] == "Termin 1.10." and p["angebot"]["angebotsnr"] == "AG1260001"


def test_projekt_lesen_erweiterte_felder(in_mock):
    in_mock["projects"] = [
        {"id": "p1", "name": "Angebot # AG1260001 [Muster GmbH]", "custom_value1": "P260010",
         "custom_value2": "RB Presse", "custom_value3": "", "custom_value4": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"},
         "number": "0012", "due_date": "2026-10-01", "private_notes": "intern", "public_notes": "extern",
         "task_rate": 95.5},
    ]
    p = t.projekt_lesen("P260010")
    assert p["in_nummer"] == "0012" and p["faellig"] == "2026-10-01"
    assert p["private_notiz"] == "intern" and p["oeffentliche_notiz"] == "extern"
    assert p["stundensatz"] == 95.5


def test_projekt_lesen_gross_klein_unabhaengig(in_mock):
    in_mock["projects"] = [
        {"id": "p1", "name": "Angebot # AG1260001 [Muster GmbH]", "custom_value1": "P260010",
         "custom_value2": "RB Presse", "custom_value3": "", "custom_value4": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"}},
    ]
    assert t.projekt_lesen("p260010")["projektnummer"] == "P260010"


def test_projekt_lesen_nicht_gefunden(in_mock):
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.projekt_lesen("P999999")


def test_projekt_kurz_stundensatz_leer_ist_none(in_mock):
    in_mock["projects"] = [
        {"id": "p1", "name": "Angebot # AG1260001 [Muster GmbH]", "custom_value1": "P260010",
         "custom_value2": "RB Presse", "custom_value3": "", "custom_value4": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"},
         "task_rate": 0},
    ]
    assert t.projekt_lesen("P260010")["stundensatz"] is None


def test_projekt_lesen_rechnungen_runden_brutto(in_mock, monkeypatch):
    in_mock["projects"] = [
        {"id": "p1", "name": "Angebot # AG1260001 [Muster GmbH]", "custom_value1": "P260010",
         "custom_value2": "RB Presse", "custom_value3": "", "custom_value4": "",
         "archived_at": 0, "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"}},
    ]
    monkeypatch.setattr(t.nn, "get_invoices_for_project", lambda pid: [
        {"number": "RG1", "date": "2026-09-01", "amount": 1190.006, "status_id": "2"}])
    r = t.projekt_lesen("P260010")["rechnungen"][0]
    assert r["brutto"] == 1190.01


def test_rechnungen_offen(in_mock):
    in_mock["invoices"] = [
        {"number": "RG1", "status_id": "2", "balance": 500, "amount": 500, "date": "2026-09-01", "due_date": "",
         "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"}},
        {"number": "RG2", "status_id": "4", "balance": 0, "amount": 800, "date": "2026-08-01", "due_date": "",
         "is_deleted": False, "client": {"name": "Muster GmbH", "number": "70001"}},
    ]
    assert [r["rechnungsnr"] for r in t.rechnungen_suchen(offen=True)["treffer"]] == ["RG1"]
    assert t.rechnungen_suchen(offen=False)["treffer"][0]["status"] == "bezahlt"


def test_rechnungen_suchen_erweiterte_felder(in_mock):
    in_mock["invoices"] = [
        {"number": "RG1", "status_id": "2", "balance": 500, "amount": 1190, "total_taxes": 190,
         "date": "2026-09-01", "due_date": "", "is_deleted": False,
         "client": {"name": "Muster GmbH", "number": "70001"},
         "po_number": "PO-5", "custom_value1": "P260010", "custom_value2": "RB Presse",
         "paid_to_date": 300},
    ]
    r = t.rechnungen_suchen()["treffer"][0]
    assert r["bestellnummer"] == "PO-5" and r["projektnummer"] == "P260010"
    assert r["projektbezeichnung"] == "RB Presse" and r["netto"] == 1000.0 and r["bezahlt"] == 300.0


def test_rechnung_lesen_mit_positionen_und_zahlung(in_mock):
    in_mock["invoices"] = [_invoice("RG1260005", discount=10, is_amount_discount=False)]
    in_mock["payments"] = [
        {"id": "pay1", "number": "ZE0001", "date": "2026-09-05", "amount": 1190.0,
         "client": {"name": "Muster GmbH", "number": "70001"}, "invoices": [{"number": "RG1260005"}],
         "paymentables": [{"invoice_id": "iRG1260005", "amount": 1190.0, "refunded": 0}],
         "transaction_reference": "TX-1", "status_id": "4", "is_deleted": False},
        {"id": "pay2", "number": "ZE0002", "date": "2026-09-06", "amount": 50.0,
         "client": {"name": "Beispiel AG", "number": "70002"}, "invoices": [{"number": "RG9"}],
         "paymentables": [{"invoice_id": "iRG9", "amount": 50.0, "refunded": 0}],
         "transaction_reference": "", "status_id": "4", "is_deleted": False},
    ]
    r = t.rechnung_lesen("rg1260005")
    assert r["rechnungsnr"] == "RG1260005" and r["positionen"][0]["produkt"] == "RB-MAVO"
    assert r["private_notiz"] == "" and r["rabatt"] == "10 %"
    assert r["zahlungen"] == [{"zahlungsnr": "ZE0001", "datum": "2026-09-05", "betrag": 1190.0,
                               "referenz": "TX-1", "status": "abgeschlossen", "erstattet": 0.0}]


def test_rechnung_lesen_zahlung_status_und_erstattung(in_mock):
    in_mock["invoices"] = [_invoice("RG1260006")]
    in_mock["payments"] = [
        {"id": "pay1", "number": "ZE0010", "date": "2026-09-05", "amount": 200.0,
         "client": {"name": "Muster GmbH", "number": "70001"}, "invoices": [{"number": "RG1260006"}],
         "paymentables": [{"invoice_id": "iRG1260006", "amount": 200.0, "refunded": 50.0}],
         "transaction_reference": "", "status_id": "5", "is_deleted": False},
    ]
    z = t.rechnung_lesen("RG1260006")["zahlungen"][0]
    assert z["status"] == "teilweise erstattet" and z["erstattet"] == 50.0


def test_rechnung_lesen_nicht_gefunden(in_mock):
    with pytest.raises(t.ToolFehler, match="RG999999 nicht gefunden"):
        t.rechnung_lesen("RG999999")


def test_zahlungen_suchen_filter_und_status(in_mock):
    in_mock["payments"] = [
        {"id": "p1", "number": "ZE0001", "date": "2026-09-01", "amount": 1190.0,
         "client": {"name": "Muster GmbH", "number": "70001"}, "invoices": [{"number": "RG1"}],
         "paymentables": [], "transaction_reference": "TX-1", "status_id": "4", "is_deleted": False},
        {"id": "p2", "number": "ZE0002", "date": "2026-09-15", "amount": 500.0,
         "client": {"name": "Beispiel AG", "number": "70002"}, "invoices": [{"number": "RG2"}],
         "paymentables": [], "transaction_reference": "", "status_id": "1", "is_deleted": False},
        {"id": "p3", "number": "ZE0003", "date": "2026-09-20", "amount": 200.0,
         "client": {"name": "Muster GmbH", "number": "70001"}, "invoices": [{"number": "RG3"}],
         "paymentables": [], "transaction_reference": "", "status_id": "4", "is_deleted": True},
    ]
    alle = t.zahlungen_suchen()["treffer"]
    assert [z["zahlungsnr"] for z in alle] == ["ZE0002", "ZE0001"]  # neueste zuerst, gelöschte raus
    assert alle[0]["status"] == "ausstehend"
    assert [z["zahlungsnr"] for z in t.zahlungen_suchen(kunde="70001")["treffer"]] == ["ZE0001"]
    assert [z["zahlungsnr"] for z in t.zahlungen_suchen(von="2026-09-10")["treffer"]] == ["ZE0002"]
    assert [z["zahlungsnr"] for z in t.zahlungen_suchen(rechnung="RG2")["treffer"]] == ["ZE0002"]


def test_lieferanten_auflisten(in_mock):
    in_mock["vendors"] = [
        {"id": "v1", "name": "Zeta GmbH", "number": "L2", "address1": "Weg 2", "postal_code": "12345",
         "city": "Stadt", "phone": "0123", "website": "zeta.de", "vat_number": "DE999",
         "contacts": [{"first_name": "Max", "last_name": "Muster", "email": "max@zeta.de", "phone": "0124"}],
         "is_deleted": False},
        {"id": "v2", "name": "Alpha AG", "number": "L1", "address1": "", "postal_code": "", "city": "",
         "phone": "", "website": "", "vat_number": "", "contacts": [], "is_deleted": False},
        {"id": "v3", "name": "Geloescht KG", "number": "L3", "contacts": [], "is_deleted": True},
    ]
    erg = t.lieferanten_auflisten()["treffer"]
    assert [v["name"] for v in erg] == ["Alpha AG", "Zeta GmbH"]  # gelöschte raus, nach Name sortiert
    zeta = erg[1]
    assert zeta["nummer"] == "L2" and zeta["ort"] == "Stadt"
    assert zeta["kontakte"] == [{"name": "Max Muster", "email": "max@zeta.de", "telefon": "0124"}]


def test_dokumente_auflisten_ohne_url_hash(in_mock):
    in_mock["quotes"] = [_quote("AG1260001")]
    erstellt = int(datetime(2026, 9, 23, 10, 0).timestamp())
    in_mock["documents"] = [
        {"name": "Angebot.pdf", "type": "pdf", "size": 204800, "created_at": erstellt, "is_public": True,
         "url": "https://x", "hash": "abc", "link": "https://y", "preview": "z"},
    ]
    d = t.dokumente_auflisten("angebot", "AG1260001")
    assert d["art"] == "angebot" and d["nummer"] == "AG1260001"
    assert d["dokumente"] == [{"name": "Angebot.pdf", "typ": "pdf", "groesse_kb": 200.0,
                               "datum": "23.09.2026", "oeffentlich": True}]
    assert d["hinweis"] == "Nur Liste; Inhalte sind über den MCP nicht abrufbar."


def test_dokumente_auflisten_ungueltige_art(in_mock):
    with pytest.raises(t.ToolFehler, match="art"):
        t.dokumente_auflisten("lieferant", "L1")


def test_dokumente_auflisten_art_gross_klein(in_mock):
    in_mock["quotes"] = [_quote("AG1260001")]
    in_mock["documents"] = []
    d = t.dokumente_auflisten(" Angebot ", "AG1260001")
    assert d["art"] == "angebot"


def test_dokumente_auflisten_datum_zeitzone_berlin(in_mock):
    """_unix_datum muss immer in Europe/Berlin rechnen, unabhängig von der Container-Zeitzone (Task 3):
    23:30 UTC liegt in Berlin (Sommerzeit, +2h) schon im nächsten Tag."""
    in_mock["quotes"] = [_quote("AG1260001")]
    ts = int(datetime(2026, 9, 22, 23, 30, tzinfo=timezone.utc).timestamp())
    in_mock["documents"] = [
        {"name": "Spaet.pdf", "type": "pdf", "size": 1024, "created_at": ts, "is_public": True,
         "is_deleted": False},
    ]
    d = t.dokumente_auflisten("angebot", "AG1260001")
    assert d["dokumente"][0]["datum"] == "23.09.2026"


def test_dokumente_auflisten_ohne_geloeschte(in_mock):
    in_mock["quotes"] = [_quote("AG1260001")]
    erstellt = int(datetime(2026, 9, 23, 10, 0).timestamp())
    in_mock["documents"] = [
        {"name": "Angebot.pdf", "type": "pdf", "size": 1024, "created_at": erstellt, "is_public": True,
         "is_deleted": False},
        {"name": "Alt.pdf", "type": "pdf", "size": 1024, "created_at": erstellt, "is_public": True,
         "is_deleted": True},
    ]
    d = t.dokumente_auflisten("angebot", "AG1260001")
    assert [x["name"] for x in d["dokumente"]] == ["Angebot.pdf"]


def test_rechnung_kurz_rundet_geldbetraege(in_mock):
    in_mock["invoices"] = [_invoice("RG1", amount=1190.006, balance=45.004)]
    r = t.rechnungen_suchen()["treffer"][0]
    assert r["brutto"] == 1190.01 and r["offen_betrag"] == 45.0


# --- Rohdaten ----------------------------------------------------------------------

def test_bereinigen_entfernt_sensible_und_leere_werte():
    roh = {"id": "c1", "number": "70001", "password": "geheim", "invitations": [{"key": "x"}],
           "contacts": [{"link": "https://x", "email": "a@b.de"}], "notes": "", "empty_list": [],
           "empty_dict": {}, "amount": 0, "flag": False}
    erg = t._bereinigen(roh)
    assert "password" not in erg and "invitations" not in erg
    assert erg["contacts"] == [{"email": "a@b.de"}]  # verschachteltes link entfernt
    assert "notes" not in erg and "empty_list" not in erg and "empty_dict" not in erg
    assert erg["amount"] == 0 and erg["flag"] is False  # 0/False sind keine "leeren" Werte
    assert erg["id"] == "c1" and erg["number"] == "70001"


def test_bereinigen_mustersperre_verschachtelt():
    """Zweite Filterebene: Fragment-Treffer (auch groß/klein) fliegen raus, egal auf welcher Ebene -
    außer der expliziten Ausnahme product_key."""
    roh = {"id": "c1", "product_key": "RB-MAVO", "contacts": [
        {"email": "a@b.de", "portal_url": "https://x", "invitation_key": "abc", "access_token": "t",
         "pdf_password": "p", "signature_base64": "sig", "oauth_user_id": "1", "client_hash": "h",
         "LINK": "https://y"}]}
    erg = t._bereinigen(roh)
    assert erg["product_key"] == "RB-MAVO"  # Ausnahme bleibt erhalten
    assert erg["contacts"] == [{"email": "a@b.de"}]


def test_bereinigen_behaelt_rabatt_schalter_und_lieferantenbezug():
    """is_amount_discount und vendor_id sind aus TECHNIK entfernt (Fix-Review Runde 1) - sie müssen
    in_rohdaten also weiterhin erreichen."""
    erg = t._bereinigen({"discount": 10, "is_amount_discount": True, "vendor_id": "v1"})
    assert erg == {"discount": 10, "is_amount_discount": True, "vendor_id": "v1"}


def test_in_rohdaten_kunde_ueber_mandant_nr(in_mock):
    in_mock["clients"][0]["custom_value1"] = "F1"
    erg = t.in_rohdaten("kunde", "F1")
    assert erg["typ"] == "kunde" and erg["daten"]["number"] == "70001"
    assert erg["custom_field_beschriftungen"] == {"client1": "Mandant-Nr.", "client2": "Sonstiges",
                                                   "contact1": "Mobil"}


def test_in_rohdaten_produkt_ueber_key(in_mock):
    in_mock["products"] = [{"id": "pr1", "product_key": "RB-MAVO", "notes": "RB", "price": 2750.0,
                            "is_deleted": False}]
    erg = t.in_rohdaten("produkt", "rb-mavo")
    assert erg["daten"]["product_key"] == "RB-MAVO"
    assert erg["custom_field_beschriftungen"] == {}  # produkt hat kein Custom-Field-Präfix


def test_in_rohdaten_unbekannter_typ(in_mock):
    with pytest.raises(t.ToolFehler, match="typ"):
        t.in_rohdaten("unbekannt", "x")


def test_in_rohdaten_nicht_gefunden(in_mock):
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.in_rohdaten("kunde", "99999")


def test_in_rohdaten_ignoriert_geloeschte(in_mock):
    in_mock["clients"][0]["is_deleted"] = True
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.in_rohdaten("kunde", "70001")


# --- Schreiben -------------------------------------------------------------------

@pytest.fixture
def schreib_mock(in_mock, monkeypatch):
    def update_contacts(cid, contacts):
        in_mock["aufrufe"].append(("contacts", cid, copy.deepcopy(contacts)))
        return {"id": cid, "contacts": [dict(c, id=c.get("id") or f"neu{i}") for i, c in enumerate(contacts)]}

    def update_client(cid, felder):
        in_mock["aufrufe"].append(("client", cid, copy.deepcopy(felder)))
        return {"id": cid, "contacts": felder.get("contacts", [])}

    monkeypatch.setattr(t.nn, "update_client_contacts", update_contacts)
    monkeypatch.setattr(t.nn, "update_client", update_client)
    monkeypatch.setattr(t.nn, "update_quote_private_notes",
                        lambda qid, text: in_mock["aufrufe"].append(("quote_notes", qid, text)) or True)
    monkeypatch.setattr(t.nn, "update_project",
                        lambda pid, felder: in_mock["aufrufe"].append(("project", pid, dict(felder))) or True)
    monkeypatch.setattr(t.nn, "create_quote",
                        lambda payload: in_mock["aufrufe"].append(("quote", payload)) or {"id": "qneu", "number": "AG1260200"})
    monkeypatch.setattr(t.nn, "mark_quote_sent", lambda qid: pytest.fail("mark_sent darf nie gerufen werden"))
    monkeypatch.setattr(t.nn, "get_products", lambda: [
        {"id": f"p{k}", "product_key": k, "notes": f"Text {k}", "price": p, "tax_name1": "MwSt.",
         "tax_rate1": 19, "tax_id": "2"}
        for k, p in (("RB-MAVO", 2750.0), ("BAMA", 1575.0), ("VKBMA", 0.0), ("AKAllg", 0.0), ("IndLeist", 0.0))])
    monkeypatch.setattr(t.nn, "update_quote_line_items",
                        lambda qid, items: in_mock["aufrufe"].append(("line_items", qid, copy.deepcopy(items)))
                        or {"id": qid})
    monkeypatch.setattr(t, "log_angebot", lambda nr, qid, cid: in_mock["log"].append((nr, qid, cid)))
    monkeypatch.setattr(t, "log", MagicMock())  # keine Testläufe im echten ab_sync.log
    monkeypatch.setattr(t.nn, "get_tax_rates", lambda: [{"id": "VolejRejNm", "name": "MwSt.", "rate": 19.0}])
    monkeypatch.setattr(t.nn, "create_product",
                        lambda payload: in_mock["aufrufe"].append(("product_create", copy.deepcopy(payload)))
                        or {"id": "pneu"})
    monkeypatch.setattr(t.nn, "update_product",
                        lambda pid, felder: in_mock["aufrufe"].append(("product_update", pid, copy.deepcopy(felder)))
                        or {"id": pid})
    return in_mock


def test_kunde_aendern_lehnt_fremde_felder_ab(schreib_mock):
    with pytest.raises(t.ToolFehler, match="name"):
        t.kunde_aendern("desktop", "70001", {"name": "Neu GmbH", "city": "Mainz"})
    assert schreib_mock["aufrufe"] == []


def test_kunde_aendern_schickt_alle_kontakte_mit(schreib_mock):
    t.kunde_aendern("desktop", "70001", {"city": "Mainz", "phone": "06151 1"})
    art, cid, felder = schreib_mock["aufrufe"][0]
    assert (art, cid) == ("client", "c1")
    assert felder["city"] == "Mainz" and [k["id"] for k in felder["contacts"]] == ["k1"]
    # Protokoll geht ins log-Attribut (hier gemockt, siehe schreib_mock), nicht ans echte ab_sync.log,
    # und trägt den Aufrufer für die Zuordnung
    meldung, aufrufer = t.log.info.call_args[0][0], t.log.info.call_args[0][1]
    assert meldung.startswith("IN-MCP [") and aufrufer == "desktop"


def test_kontakt_neu_behaelt_bestehende(schreib_mock):
    text = t.kontakt_speichern("hermes", "70001", "Bernd", "Neu", "bernd@muster.de", "Herr")
    _, _, kontakte = schreib_mock["aufrufe"][0]
    assert [k.get("id") for k in kontakte] == ["k1", None]
    assert kontakte[1]["custom_value4"] == "Herr" and "angelegt" in text


def test_kontakt_doppelte_email_abgelehnt(schreib_mock):
    with pytest.raises(t.ToolFehler, match="k1"):
        t.kontakt_speichern("desktop", "70001", "Anna", "Alt", "ANNA@muster.de", "Frau")


def test_kontakt_aendern_nur_dieser(schreib_mock):
    t.kontakt_speichern("desktop", "70001", "Anna", "Neu", "anna@muster.de", "Frau", kontakt_id="k1")
    _, _, kontakte = schreib_mock["aufrufe"][0]
    assert len(kontakte) == 1 and kontakte[0]["id"] == "k1" and kontakte[0]["last_name"] == "Neu"
    with pytest.raises(t.ToolFehler, match="k9"):
        t.kontakt_speichern("desktop", "70001", "X", "Y", "x@y.de", "Herr", kontakt_id="k9")


def test_kunde_lesen_mit_mobil_position_abteilung(in_mock):
    in_mock["clients"][0]["contacts"][0].update(custom_value1="0170-1", custom_value2="Leitung",
                                                custom_value3="Technik")
    k = t.kunde_lesen("70001")["kontakte"][0]
    assert (k["mobil"], k["position"], k["abteilung"]) == ("0170-1", "Leitung", "Technik")


def test_kontakt_aendern_behaelt_nicht_angegebene_felder(schreib_mock):
    schreib_mock["clients"][0]["contacts"][0].update(phone="06151 1", custom_value1="0170-1",
                                                     custom_value2="Leitung")
    t.kontakt_speichern("desktop", "70001", "Anna", "Alt", "anna@muster.de", "Frau", kontakt_id="k1",
                        abteilung="Technik")
    _, _, kontakte = schreib_mock["aufrufe"][0]
    k = kontakte[0]
    assert (k["phone"], k["custom_value1"], k["custom_value2"], k["custom_value3"]) == \
        ("06151 1", "0170-1", "Leitung", "Technik")


def test_kontakt_neu_mit_mobil_und_position(schreib_mock):
    t.kontakt_speichern("desktop", "70001", "Bernd", "Neu", "bernd@muster.de", "Herr",
                        mobil="0171-2", position="Einkauf")
    _, _, kontakte = schreib_mock["aufrufe"][0]
    assert (kontakte[1]["custom_value1"], kontakte[1]["custom_value2"]) == ("0171-2", "Einkauf")
    assert kontakte[1]["custom_value4"] == "Herr"


def test_kontakt_ungueltige_anrede(schreib_mock):
    with pytest.raises(t.ToolFehler, match="Anrede"):
        t.kontakt_speichern("desktop", "70001", "X", "Y", "x@y.de", "Divers")


def test_kontakt_email_aendern_ohne_flag_abgelehnt(schreib_mock):
    """M1: Die E-Mail eines bestehenden Kontakts darf nicht ohne ausdrücklichen Zusatzwunsch wandern -
    sonst könnte eine per Prompt-Injection untergeschobene Adresse künftige Rechnungen/Belege abgreifen."""
    with pytest.raises(t.ToolFehler, match="email_aendern"):
        t.kontakt_speichern("desktop", "70001", "Anna", "Alt", "angreifer@fremd.tld", "Frau", kontakt_id="k1")
    assert schreib_mock["aufrufe"] == []


def test_kontakt_email_aendern_mit_flag_erlaubt(schreib_mock):
    t.kontakt_speichern("desktop", "70001", "Anna", "Alt", "neu@muster.de", "Frau", kontakt_id="k1",
                        email_aendern=True)
    _, _, kontakte = schreib_mock["aufrufe"][0]
    assert kontakte[0]["email"] == "neu@muster.de"


def test_kontakt_email_unveraendert_andere_schreibweise_ohne_flag(schreib_mock):
    """Groß-/Kleinschreibung allein ist keine Änderung - darf ohne email_aendern durchgehen."""
    t.kontakt_speichern("desktop", "70001", "Anna", "Alt", "ANNA@MUSTER.DE", "Frau", kontakt_id="k1")
    _, _, kontakte = schreib_mock["aufrufe"][0]
    assert kontakte[0]["email"] == "ANNA@MUSTER.DE"


def test_notiz_anhaengen_erhaelt_bestand(schreib_mock):
    schreib_mock["quotes"] = [_quote("AG1260001", private_notes="alt")]
    t.notiz_setzen("desktop", "AG1260001", "Kunde ruft zurück", heute=HEUTE)
    assert schreib_mock["aufrufe"][-1] == ("quote_notes", "qAG1260001", "alt\n23.09.2026: Kunde ruft zurück")
    t.notiz_setzen("desktop", "AG1260001", "neu", modus="ersetzen", heute=HEUTE)
    assert schreib_mock["aufrufe"][-1] == ("quote_notes", "qAG1260001", "23.09.2026: neu")


def test_notiz_am_projekt(schreib_mock):
    schreib_mock["projects"] = [{"id": "p1", "name": "Angebot # AG1260001", "custom_value1": "P260010",
                                 "custom_value4": "", "is_deleted": False}]
    t.notiz_setzen("hermes", "P260010", "Termin 2.10.", heute=HEUTE)
    assert schreib_mock["aufrufe"][-1] == ("project", "p1", {"custom_value4": "23.09.2026: Termin 2.10."})
    with pytest.raises(t.ToolFehler, match="modus"):
        t.notiz_setzen("hermes", "P260010", "x", modus="loeschen")


def test_notiz_am_projekt_ohne_in_konfiguration(schreib_mock, monkeypatch):
    schreib_mock["projects"] = [{"id": "p1", "name": "Angebot # AG1260001", "custom_value1": "P260010",
                                 "custom_value4": "", "is_deleted": False}]
    monkeypatch.setattr(t.nn, "update_project", lambda pid, felder: False)
    with pytest.raises(t.ToolFehler, match="nicht konfiguriert"):
        t.notiz_setzen("hermes", "P260010", "Termin 2.10.", heute=HEUTE)


def test_entwurf_ohne_mark_sent_mit_log(schreib_mock):
    text = t.angebotsentwurf_anlegen(
        "desktop", "70001", ["anna@muster.de"], [{"produkt": "RB-MAVO"}, {"produkt": "BAMA", "menge": 2}],
        "Risikobeurteilung Presse", heute=HEUTE)
    art, payload = schreib_mock["aufrufe"][0]
    assert art == "quote" and payload["client_id"] == "c1"
    assert [i["product_key"] for i in payload["line_items"]] == ["RB-MAVO", "BAMA", "VKBMA"]
    assert payload["invitations"] == [{"client_contact_id": "k1"}]
    assert payload["due_date"] == "2026-10-07"  # Standard 14 Tage
    assert "custom_value3" not in payload and "custom_value4" not in payload
    assert schreib_mock["log"] == [("AG1260200", "qneu", "c1")]
    assert "AG1260200" in text and "5900.00" in text


def test_entwurf_log_angebot_fehlschlag_meldet_trotzdem_erfolg(schreib_mock, monkeypatch):
    def kaputt(nr, qid, cid):
        raise RuntimeError("DB weg")
    monkeypatch.setattr(t, "log_angebot", kaputt)
    text = t.angebotsentwurf_anlegen(
        "desktop", "70001", ["anna@muster.de"], [{"produkt": "RB-MAVO"}], "Risikobeurteilung Presse", heute=HEUTE)
    assert [a[0] for a in schreib_mock["aufrufe"] if a[0] == "quote"] == ["quote"]  # nur einmal angelegt
    assert "AG1260200" in text
    assert "Hinweis: Eintrag ins angebot_log fehlgeschlagen" in text


def test_entwurf_ungueltige_menge(schreib_mock):
    with pytest.raises(t.ToolFehler, match="RB-MAVO: Menge"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["anna@muster.de"],
                                  [{"produkt": "RB-MAVO", "menge": 0}], "X", heute=HEUTE)
    with pytest.raises(t.ToolFehler, match="RB-MAVO: Menge"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["anna@muster.de"],
                                  [{"produkt": "RB-MAVO", "menge": "abc"}], "X", heute=HEUTE)
    assert schreib_mock["aufrufe"] == []


def test_entwurf_ungueltiger_preis(schreib_mock):
    with pytest.raises(t.ToolFehler, match="RB-MAVO: Preis"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["anna@muster.de"],
                                  [{"produkt": "RB-MAVO", "preis": -5}], "X", heute=HEUTE)
    assert schreib_mock["aufrufe"] == []


def test_entwurf_unbekannter_empfaenger(schreib_mock):
    with pytest.raises(t.ToolFehler, match="fremd@x.de"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["fremd@x.de"], [{"produkt": "RB-MAVO"}], "X", heute=HEUTE)
    assert schreib_mock["aufrufe"] == []


def test_entwurf_unbekanntes_produkt_und_gueltigkeit(schreib_mock):
    with pytest.raises(t.ToolFehler, match="GIBTS"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["anna@muster.de"], [{"produkt": "GIBTS"}], "X", heute=HEUTE)
    with pytest.raises(t.ToolFehler, match="höchstens 60"):
        t.angebotsentwurf_anlegen("desktop", "70001", ["anna@muster.de"], [{"produkt": "RB-MAVO"}], "X",
                                  gueltig_bis="2026-12-31", heute=HEUTE)
    assert schreib_mock["aufrufe"] == []


def test_positionen_bauen_ueberspringt_vkb_und_uebernimmt_angaben(schreib_mock):
    produkte = {p["product_key"]: p for p in t.nn.get_products()}
    liste = t._positionen_bauen(
        [{"produkt": "VKBMA"}, {"produkt": "BAMA", "menge": 2, "preis": 100, "text": "Neu"}, {"produkt": "RB-MAVO"}],
        produkte)
    assert [(p["product_key"], p["quantity"], p["cost"], p["notes"]) for p in liste] == [
        ("BAMA", 2.0, 100.0, "Neu"), ("RB-MAVO", 1.0, 2750.0, "Text RB-MAVO")]
    assert all(p["tax_rate1"] == 19 and not p["fest"] for p in liste)


def test_positionen_bauen_produktschluessel_gross_klein(schreib_mock):
    """F5: Produktschlüssel wird case-insensitiv auf den kanonischen Katalog-Key abgebildet."""
    produkte = {p["product_key"]: p for p in t.nn.get_products()}
    liste = t._positionen_bauen([{"produkt": "bama"}], produkte)
    assert liste[0]["product_key"] == "BAMA"


def _entwurf(stand, nr="AG1260300", status="1", vkb="AKAllg", **extra):
    items = [{"product_key": "RB-MAVO", "notes": "Eigener Text", "quantity": 1, "cost": 2500,
              "tax_name1": "MwSt.", "tax_rate1": 16, "tax_id": "2"}]
    if vkb:
        items.append({"product_key": vkb, "notes": "AGB", "quantity": 1, "cost": 0,
                      "tax_name1": "MwSt.", "tax_rate1": 19, "tax_id": "2"})
    q = _quote(nr, status=status, line_items=items, **extra)
    stand["quotes"].append(q)
    return q


def _line_item_aufrufe(stand):
    return [a for a in stand["aufrufe"] if a[0] == "line_items"]


def test_positionen_setzen_nur_entwurf(schreib_mock):
    for i, status in enumerate(("2", "3", "4", "-1")):
        _entwurf(schreib_mock, nr=f"AG126031{i}", status=status)
        with pytest.raises(t.ToolFehler, match="nicht Entwurf"):
            t.angebotsentwurf_positionen_setzen("desktop", f"AG126031{i}", [{"produkt": "BAMA"}])
    _entwurf(schreib_mock, nr="AG1260320", archived_at=1700000000)
    with pytest.raises(t.ToolFehler, match="archiviert"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260320", [{"produkt": "BAMA"}])
    _entwurf(schreib_mock, nr="AG1260321", custom_value3="yes")
    with pytest.raises(t.ToolFehler, match="bestellt"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260321", [{"produkt": "BAMA"}])
    _entwurf(schreib_mock, nr="AG1260322", custom_value4="yes")
    with pytest.raises(t.ToolFehler, match="als abgeschlossen markiert"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260322", [{"produkt": "BAMA"}])
    assert _line_item_aufrufe(schreib_mock) == []


def test_positionen_setzen_ersetzt_liste_mwst_aus_katalog(schreib_mock):
    _entwurf(schreib_mock)
    text = t.angebotsentwurf_positionen_setzen(
        "desktop", "ag1260300",
        [{"produkt": "RB-MAVO", "text": "Eigener Text", "preis": 2500}, {"produkt": "BAMA", "menge": 2}])
    (art, qid, items), = _line_item_aufrufe(schreib_mock)
    assert qid == "qAG1260300"
    assert [i["product_key"] for i in items] == ["RB-MAVO", "BAMA", "AKAllg"]
    assert items[0]["notes"] == "Eigener Text" and items[0]["cost"] == 2500.0
    assert items[0]["tax_rate1"] == 19  # alte Position trug 16 - MwSt. kommt aus dem Katalog
    assert items[1]["notes"] == "Text BAMA" and items[1]["quantity"] == 2.0
    assert "3 Positionen" in text and "1000.00 € → 5650.00 €" in text and "Entwurf" in text
    schreib_mock_log = t.log.info.call_args[0]
    assert schreib_mock_log[1:] == ("desktop", "AG1260300", 3)


def test_positionen_setzen_summen_aus_in(schreib_mock, monkeypatch):
    """F2: Die "nachher"-Summen kommen aus der Rückgabe von update_quote_line_items (IN), nicht aus der
    lokalen Berechnung. Die IN-Werte weichen hier bewusst von der lokalen Rechnung ab (BAMA allein wäre
    lokal 1575.00 € netto), damit belegt ist, dass die IN-Zahl gemeldet wird."""
    _entwurf(schreib_mock)
    monkeypatch.setattr(t.nn, "update_quote_line_items",
                        lambda qid, items: {"id": qid, "amount": 5950.0, "total_taxes": 950.0})
    text = t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "BAMA"}])
    assert "5000.00 €" in text and "5950.00 €" in text


def test_positionen_setzen_verkaufsbedingungen(schreib_mock):
    _entwurf(schreib_mock)  # trägt AKAllg
    t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "BAMA"}, {"produkt": "VKBMA"}])
    items = _line_item_aufrufe(schreib_mock)[-1][2]
    assert [i["product_key"] for i in items] == ["BAMA", "AKAllg"]  # übergebene VKB übersprungen, bisherige bleibt
    t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "BAMA"}], verkaufsbedingungen="VKBMA")
    assert [i["product_key"] for i in _line_item_aufrufe(schreib_mock)[-1][2]] == ["BAMA", "VKBMA"]
    _entwurf(schreib_mock, nr="AG1260301", vkb="")
    t.angebotsentwurf_positionen_setzen("desktop", "AG1260301", [{"produkt": "BAMA"}])
    assert [i["product_key"] for i in _line_item_aufrufe(schreib_mock)[-1][2]] == ["BAMA", "VKBMA"]


def test_positionen_setzen_ablehnungen(schreib_mock):
    _entwurf(schreib_mock)
    with pytest.raises(t.ToolFehler, match="GIBTS"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "GIBTS"}])
    with pytest.raises(t.ToolFehler, match="BAMA: Menge"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "BAMA", "menge": 0}])
    with pytest.raises(t.ToolFehler, match="IndLeist: Bitte einen Betrag"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "IndLeist", "text": "Sonder"}])
    with pytest.raises(t.ToolFehler, match="mindestens eine Leistung"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [])
    with pytest.raises(t.ToolFehler, match="verkaufsbedingungen"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1260300", [{"produkt": "BAMA"}], verkaufsbedingungen="XYZ")
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.angebotsentwurf_positionen_setzen("desktop", "AG1269999", [{"produkt": "BAMA"}])
    assert _line_item_aufrufe(schreib_mock) == []


def test_produkte_auflisten_mit_steuer(schreib_mock):
    rb = next(p for p in t.produkte_auflisten() if p["produkt"] == "RB-MAVO")
    assert rb == {"produkt": "RB-MAVO", "text": "Text RB-MAVO", "preis": 2750.0, "mwst": 19, "steuer": "MwSt."}


def test_produkt_aendern_nur_angegebene_felder(schreib_mock):
    text = t.produkt_speichern("desktop", "BAMA", preis=1600)
    assert schreib_mock["aufrufe"] == [("product_update", "pBAMA", {"price": 1600.0})]
    assert "geändert" in text and "Bestehende Angebote bleiben unverändert" in text
    t.produkt_speichern("desktop", "bama", text=" Neuer Text ")  # Schlüssel ohne Rücksicht auf Groß/klein
    assert schreib_mock["aufrufe"][-1] == ("product_update", "pBAMA", {"notes": "Neuer Text"})


def test_produkt_mwst_ohne_tax_id(schreib_mock):
    t.produkt_speichern("desktop", "VKBMA", mwst="MwSt.")  # VKB bewusst nicht gesperrt
    assert schreib_mock["aufrufe"][-1] == ("product_update", "pVKBMA", {"tax_name1": "MwSt.", "tax_rate1": 19.0})


def test_produkt_neu_komplett_mit_steuerkategorie(schreib_mock):
    text = t.produkt_speichern("desktop", "NEU1", text="Neue Leistung", preis=100, mwst="19 %")
    assert schreib_mock["aufrufe"] == [("product_create", {
        "product_key": "NEU1", "notes": "Neue Leistung", "price": 100.0,
        "tax_name1": "MwSt.", "tax_rate1": 19.0, "tax_id": "2"})]
    assert "NEU1 angelegt" in text


def test_produkt_neu_lehnt_schluessel_mit_steuerzeichen_ab(schreib_mock):
    """L1: Ein Zeilenumbruch im Key könnte eine gefälschte Zeile ins gemeinsame Audit-Log schmuggeln."""
    with pytest.raises(t.ToolFehler, match="Produktschlüssel darf nur"):
        t.produkt_speichern("desktop", "NEU1\n2026-09-23 | INFO | Fake-Zeile", text="X", preis=1, mwst="19")
    assert schreib_mock["aufrufe"] == []


def test_produkt_neu_lehnt_zu_langen_schluessel_ab(schreib_mock):
    with pytest.raises(t.ToolFehler, match="höchstens 100 Zeichen"):
        t.produkt_speichern("desktop", "N" * 101, text="X", preis=1, mwst="19")
    assert schreib_mock["aufrufe"] == []


def test_produkt_ablehnungen(schreib_mock):
    with pytest.raises(t.ToolFehler, match="fehlen: preis, mwst"):
        t.produkt_speichern("desktop", "NEU1", text="Nur Text")
    with pytest.raises(t.ToolFehler, match="Keine Felder"):
        t.produkt_speichern("desktop", "BAMA")
    with pytest.raises(t.ToolFehler, match="Preis muss eine Zahl ab 0"):
        t.produkt_speichern("desktop", "BAMA", preis=-1)
    with pytest.raises(t.ToolFehler, match="Preis muss eine Zahl ab 0"):
        t.produkt_speichern("desktop", "BAMA", preis="abc")
    with pytest.raises(t.ToolFehler, match="Produktschlüssel ist leer"):
        t.produkt_speichern("desktop", "  ", text="X")
    with pytest.raises(t.ToolFehler, match="Produkttext ist leer"):
        t.produkt_speichern("desktop", "BAMA", text="  ")
    with pytest.raises(t.ToolFehler, match="'7' gibt es nicht. Vorhanden: MwSt. 19 %"):
        t.produkt_speichern("desktop", "BAMA", mwst="7")
    assert schreib_mock["aufrufe"] == []


def test_produkt_mwst_mehrdeutig(schreib_mock, monkeypatch):
    monkeypatch.setattr(t.nn, "get_tax_rates", lambda: [
        {"id": "a", "name": "MwSt.", "rate": 19.0}, {"id": "b", "name": "USt. Sonder", "rate": 19.0}])
    with pytest.raises(t.ToolFehler, match="nicht eindeutig"):
        t.produkt_speichern("desktop", "BAMA", mwst="19")
    t.produkt_speichern("desktop", "BAMA", mwst="USt. Sonder")  # über den Namen eindeutig
    assert schreib_mock["aufrufe"][-1] == ("product_update", "pBAMA", {"tax_name1": "USt. Sonder", "tax_rate1": 19.0})


# --- Server ----------------------------------------------------------------------

def test_middleware_lehnt_ohne_gueltiges_token_ab(monkeypatch):
    pytest.importorskip("fastmcp")
    from starlette.testclient import TestClient
    from in_mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "TOKENS", {"desktop": "richtig"})
    client = TestClient(mcp_server.baue_app(mcp_server.baue_mcp(t.K)))
    assert client.post("/mcp", json={}).status_code == 401
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer falsch"}).status_code == 401
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer "}).status_code == 401


@pytest.fixture
def mcp_server_mod(monkeypatch):
    """mcp_server mit gemocktem log, damit die Fehlerpfad-Tests nicht ins echte ab_sync.log schreiben."""
    pytest.importorskip("fastmcp")
    from in_mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "log", MagicMock())
    return mcp_server


def _http_fehler(status: int, body: bytes = b"") -> requests.HTTPError:
    antwort = requests.Response()
    antwort.status_code = status
    antwort._content = body
    return requests.HTTPError(response=antwort)


def test_sicher_toolfehler_durchgereicht(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher
    def lesen():
        raise t.ToolFehler("Kunde 70099 nicht gefunden.")

    with pytest.raises(ToolError, match="Kunde 70099 nicht gefunden."):
        lesen()


def test_sicher_lesend_timeout_meldung(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher
    def lesen():
        raise requests.Timeout()

    with pytest.raises(ToolError, match="später erneut versuchen"):
        lesen()


def test_sicher_schreibend_timeout_ergebnis_unklar(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher(schreibend=True)
    def schreiben():
        raise requests.ConnectionError()

    with pytest.raises(ToolError, match="Ergebnis unklar"):
        schreiben()


def test_sicher_422_liest_message_und_errors(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher
    def schreiben():
        raise _http_fehler(422, b'{"message": "Fehlerhafte Anfrage", "errors": {"email": ["ist ung\\u00fcltig"]}}')

    with pytest.raises(ToolError) as exc:
        schreiben()
    text = str(exc.value)
    assert "Fehlerhafte Anfrage" in text and "email: ist ungültig" in text


def test_sicher_500_ohne_body_in_meldung(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher
    def lesen():
        raise _http_fehler(500, b"<html>Interner Serverfehler, Stacktrace ABC</html>")

    with pytest.raises(ToolError) as exc:
        lesen()
    text = str(exc.value)
    assert text == "Invoice Ninja meldet einen Serverfehler (500)."
    assert "Stacktrace" not in text


def test_sicher_5xx_schreibend_haengt_pruefhinweis_an(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher(schreibend=True)
    def schreiben():
        raise _http_fehler(503, b"nicht wichtig")

    with pytest.raises(ToolError, match="Bitte vor einem erneuten Versuch prüfen"):
        schreiben()


def test_sicher_generischer_fehler_ohne_traceback(mcp_server_mod):
    from fastmcp.exceptions import ToolError

    @mcp_server_mod._sicher
    def lesen():
        raise ValueError("geheimes Detail xyz")

    with pytest.raises(ToolError) as exc:
        lesen()
    text = str(exc.value)
    assert text == "Interner Fehler im IN-MCP, Details im Log des IN-MCP."
    assert "geheimes Detail xyz" not in text


LESENDE_TOOLS = {"kunden_suchen", "kunde_lesen", "angebote_suchen", "angebot_lesen", "projekte_suchen",
                 "projekt_lesen", "rechnungen_suchen", "rechnung_lesen", "zahlungen_suchen",
                 "lieferanten_auflisten", "dokumente_auflisten", "produkte_auflisten",
                 "angebot_vorlagen_auflisten", "in_rohdaten"}
SCHREIBENDE_TOOLS = {"kontakt_speichern", "kunde_aendern", "notiz_setzen", "angebotsentwurf_anlegen",
                     "angebotsentwurf_positionen_setzen", "produkt_speichern"}
# L4: angebotsentwurf_anlegen legt nur neu an (additiv), die übrigen Schreib-Tools überschreiben
# bestehende Daten (E-Mail/Telefon, Kundenfelder, Notiz, Positionen, Katalogwerte).
ADDITIVE_TOOLS = {"angebotsentwurf_anlegen"}


def test_readonly_hint_markiert_lesende_und_schreibende_tools(mcp_server_mod, monkeypatch):
    """MCP-Clients können anhand readOnlyHint/destructiveHint entscheiden, wie nachdrücklich sie
    einen Tool-Aufruf bestätigen lassen."""
    import asyncio
    monkeypatch.setenv("PMS_DB_PATH", "/tmp/gibtsnicht.db")      # Vorlagen-Tool nur mit PMS
    tools = asyncio.run(mcp_server_mod.baue_mcp(t.K).list_tools())
    namen = {tool.name for tool in tools}
    assert namen == LESENDE_TOOLS | SCHREIBENDE_TOOLS
    for tool in tools:
        if tool.name in LESENDE_TOOLS:
            assert tool.annotations is not None and tool.annotations.readOnlyHint is True
        else:
            assert tool.annotations is not None and tool.annotations.readOnlyHint is False
            erwartet = tool.name not in ADDITIVE_TOOLS
            assert tool.annotations.destructiveHint is erwartet


def test_dss_tools_zeigen_alle_argumente(mcp_server_mod, monkeypatch):
    import asyncio
    monkeypatch.delenv("PMS_DB_PATH", raising=False)
    tools = {tool.name: tool for tool in asyncio.run(mcp_server_mod.baue_mcp(t.K).list_tools())}
    assert "angebot_vorlagen_auflisten" not in tools
    assert {"anrede", "mobil", "position", "abteilung"} <= set(tools["kontakt_speichern"].parameters["properties"])
    assert "bestellt" in tools["angebote_suchen"].parameters["properties"]
    assert "verkaufsbedingungen" in tools["angebotsentwurf_anlegen"].parameters["properties"]


def test_tokens_aus_umgebung():
    from in_mcp import server as mcp_server
    env = {"MCP_TOKEN_DESKTOP": "a", "MCP_TOKEN_HERMES": "b", "MCP_TOKEN_LEER": "", "MCP_TOKEN_": "c",
           "IN_MCP_TOKEN_ALT": "d", "PATH": "/bin"}
    assert mcp_server.tokens_aus_umgebung(env) == {"desktop": "a", "hermes": "b"}


def test_anweisungen_dss():
    from in_mcp import server as mcp_server
    text = mcp_server.anweisungen(t.K)
    assert "DSS-Siegmund" in text and "VKBMA, AKAllg" in text and "14 bis 60 Tage" in text
    assert "'Herr' oder 'Frau'" in text and "(AG…)" in text


def test_dss_zusatzfelder_nur_freie_felder(in_mock):
    in_mock["clients"][0]["custom_value2"] = "Bonität A"
    k = t.kunde_lesen("70001")
    assert k["zusatzfelder"] == {"Sonstiges": "Bonität A"}
    assert "zusatzfelder" not in k["kontakte"][0]


# --- L2/L3: Betrieb (forwarded_allow_ips, non-root Container) ----------------------


def _main_umgebung(monkeypatch, mcp_server_mod):
    """Minimalumgebung, mit der main() durchläuft, ohne echtes IN oder eine echte Log-Datei."""
    monkeypatch.setattr(mcp_server_mod, "TOKENS", {})
    monkeypatch.setattr(mcp_server_mod.protokoll, "einrichten", MagicMock())
    monkeypatch.setenv("MCP_TOKEN_DESKTOP", "geheim")
    monkeypatch.setenv("INVOICE_NINJA_URL", "https://in.example.de")
    monkeypatch.setenv("INVOICE_NINJA_API_TOKEN", "tok")
    monkeypatch.setenv("INSTANZ_KONFIG", str(BEISPIELE / "instanz.neutral.yaml"))
    monkeypatch.delenv("PMS_DB_PATH", raising=False)
    lauf = MagicMock()
    monkeypatch.setattr(mcp_server_mod.uvicorn, "run", lauf)
    return lauf


def test_main_forwarded_allow_ips_default(mcp_server_mod, monkeypatch):
    """L2: Ohne Proxy davor soll niemand seine IP im Access-Log über X-Forwarded-For fälschen können."""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    lauf = _main_umgebung(monkeypatch, mcp_server_mod)
    mcp_server_mod.main()
    assert lauf.call_args.kwargs["forwarded_allow_ips"] == "127.0.0.1"


def test_main_forwarded_allow_ips_aus_umgebung(mcp_server_mod, monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.18.0.1")
    lauf = _main_umgebung(monkeypatch, mcp_server_mod)
    mcp_server_mod.main()
    assert lauf.call_args.kwargs["forwarded_allow_ips"] == "172.18.0.1"


def test_dockerfile_laeuft_nicht_als_root():
    """L3: Nur relevant zusammen mit einer RCE in FastMCP/uvicorn/requests - der Prozess soll dann
    nicht root sein und keinen Root-Schreibzugriff auf das gemountete Datenverzeichnis haben."""
    text = (REPO / "Dockerfile").read_text()
    assert "useradd" in text
    assert "\nUSER app\n" in text or text.rstrip().endswith("USER app")
    # USER muss NACH dem chown des Datenverzeichnisses stehen, sonst bleibt /data root-eigen
    assert text.index("USER app") > text.index("chown")

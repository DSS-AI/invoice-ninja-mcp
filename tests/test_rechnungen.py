"""Tests für die Rechnungs-Tools (Entwürfe, Umwandeln, Status, Versand, Storno).

Eigener In-Memory-Mock von Invoice Ninja; nie gegen das echte IN. conftest.py setzt die
DSS-Konfiguration (alle vier Rechnungs-Rechte an)."""
import asyncio
import copy
import dataclasses
from datetime import date
from unittest.mock import MagicMock

import pytest

from in_mcp import tools as t

HEUTE = date(2026, 9, 24)
HINWEIS = "Rechnungsnummer ist vergeben. Nicht löschen – eine falsche Rechnung stornieren."

KUNDE = {"id": "c1", "number": "70001", "name": "Muster GmbH", "city": "Darmstadt", "custom_value1": "",
         "contacts": [{"id": "k1", "first_name": "Anna", "last_name": "Alt", "email": "anna@muster.de"},
                      {"id": "k2", "first_name": "Bernd", "last_name": "Bau", "email": "bernd@muster.de"},
                      {"id": "k3", "first_name": "Ohne", "last_name": "Mail", "email": ""}]}
ANDERER = {"id": "c2", "number": "70002", "name": "Beispiel AG", "city": "Mainz", "custom_value1": "",
           "contacts": []}
PROJEKT = {"id": "pr1", "number": "0007", "name": "Angebot # AG9990100 [Muster GmbH]", "client_id": "c1",
           "custom_value1": "P260050", "custom_value2": "RB Presse", "is_deleted": False,
           "client": {"name": "Muster GmbH", "number": "70001"}}
FREMDPROJEKT = dict(PROJEKT, id="pr2", number="0008", client_id="c2", custom_value1="P260051")

KATALOG = [{"id": f"p{k}", "product_key": k, "notes": f"Text {k}", "price": p, "tax_name1": "MwSt.",
            "tax_rate1": 19, "tax_id": "2"}
           for k, p in (("RB-MAVO", 1000.0), ("BAMA", 500.0), ("VKBMA", 0.0), ("AKAllg", 0.0),
                        ("IndLeist", 0.0))]


def _invoice(nr, status="1", balance=0.0, **extra):
    i = {"id": f"i{nr}", "number": nr, "status_id": status, "client_id": "c1", "date": "2026-09-20",
         "due_date": "2026-10-04", "amount": 1190.0, "total_taxes": 190.0, "balance": balance,
         "po_number": "", "private_notes": "", "public_notes": "", "archived_at": 0, "is_deleted": False,
         "client": {"name": "Muster GmbH", "number": "70001"},
         "invitations": [{"id": "inv1", "client_contact_id": "k1"}],
         "line_items": [{"product_key": "RB-MAVO", "notes": "RB", "quantity": 1, "cost": 1000, "tax_rate1": 19}]}
    i.update(extra)
    return i


def _quote(nr, status="2", **extra):
    q = {"id": f"q{nr}", "number": nr, "status_id": status, "invoice_id": "", "is_deleted": False,
         "archived_at": 0, "amount": 1190.0, "total_taxes": 190.0, "client": {"name": "Muster GmbH"}}
    q.update(extra)
    return q


@pytest.fixture
def rn(monkeypatch):
    """Invoice Ninja im Speicher. Schreibaufrufe landen in `aufrufe`."""
    stand = {"clients": [copy.deepcopy(KUNDE), copy.deepcopy(ANDERER)], "quotes": [],
             "projects": [copy.deepcopy(PROJEKT), copy.deepcopy(FREMDPROJEKT)],
             "invoices": [], "aufrufe": []}

    def finde_invoice(iid):
        return next(i for i in stand["invoices"] if i["id"] == iid)

    monkeypatch.setattr(t.nn, "get_all_clients", lambda: copy.deepcopy(stand["clients"]))
    monkeypatch.setattr(t.nn, "get_client",
                        lambda cid: copy.deepcopy(next(c for c in stand["clients"] if c["id"] == cid)))
    monkeypatch.setattr(t.nn, "get_quotes_listing", lambda: copy.deepcopy(stand["quotes"]))
    monkeypatch.setattr(t.nn, "get_projects_listing", lambda: copy.deepcopy(stand["projects"]))
    monkeypatch.setattr(t.nn, "get_invoices_listing", lambda: copy.deepcopy(stand["invoices"]))
    monkeypatch.setattr(t.nn, "get_invoice", lambda iid: copy.deepcopy(finde_invoice(iid)))
    monkeypatch.setattr(t.nn, "get_products", lambda: copy.deepcopy(KATALOG))

    def create_invoice(payload):
        stand["aufrufe"].append(("create_invoice", copy.deepcopy(payload)))
        neu = _invoice("RG9990089", id="ineu", amount=1785.0, total_taxes=285.0)
        stand["invoices"].append(neu)
        return copy.deepcopy(neu)

    def update_invoice(iid, felder):
        stand["aufrufe"].append(("update_invoice", iid, copy.deepcopy(felder)))
        return {"id": iid, "amount": 595.0, "total_taxes": 95.0}

    def invoice_bulk(action, ids):
        stand["aufrufe"].append(("invoice_bulk", action, list(ids)))
        neuer_status = {"mark_sent": "2", "email": "2", "cancel": "5"}[action]
        for i in stand["invoices"]:
            if i["id"] in ids and not (action == "email" and i["status_id"] != "1"):
                i["status_id"] = neuer_status
        return [copy.deepcopy(finde_invoice(x)) for x in ids]

    def create_payment(payload):
        stand["aufrufe"].append(("create_payment", copy.deepcopy(payload)))
        return {"id": "zneu", "number": "0042", "amount": payload["amount"]}

    def quote_bulk(action, ids):
        stand["aufrufe"].append(("quote_bulk", action, list(ids)))
        for q in stand["quotes"]:
            if q["id"] in ids:
                q.update(invoice_id="iumg", status_id="4")
        stand["invoices"].append(_invoice("RG9990090", id="iumg"))
        return []

    monkeypatch.setattr(t.nn, "create_invoice", create_invoice)
    monkeypatch.setattr(t.nn, "update_invoice", update_invoice)
    monkeypatch.setattr(t.nn, "invoice_bulk", invoice_bulk)
    monkeypatch.setattr(t.nn, "create_payment", create_payment)
    monkeypatch.setattr(t.nn, "quote_bulk", quote_bulk)
    monkeypatch.setattr(t, "log", MagicMock())  # keine Testläufe im echten Log
    return stand


def _log_zeile():
    args = t.log.info.call_args[0]
    return args[0] % args[1:]


# --- rechnungsentwurf_anlegen ------------------------------------------------------

def test_anlegen_minimal_payload_ohne_invitations(rn):
    text = t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "RB-MAVO"}, {"produkt": "BAMA"}])
    art, payload = rn["aufrufe"][0]
    assert art == "create_invoice"
    assert payload == {"client_id": "c1", "line_items": [
        {"product_key": "RB-MAVO", "notes": "Text RB-MAVO", "quantity": 1.0, "cost": 1000.0,
         "tax_name1": "MwSt.", "tax_rate1": 19, "tax_id": "2", "type_id": "1"},
        {"product_key": "BAMA", "notes": "Text BAMA", "quantity": 1.0, "cost": 500.0,
         "tax_name1": "MwSt.", "tax_rate1": 19, "tax_id": "2", "type_id": "1"}]}
    assert "RG9990089" in text and HINWEIS in text
    assert "1500.00 € netto" in text and "1785.00 € brutto" in text   # Summen aus der IN-Antwort
    assert _log_zeile() == "IN-MCP [desktop] rechnungsentwurf_anlegen RG9990089 für 70001"


def test_anlegen_alle_felder_mit_projekt(rn):
    t.rechnungsentwurf_anlegen("hermes", "70001", [{"produkt": "RB-MAVO", "menge": 2, "preis": 900,
                                                    "text": "Eigener Text"}],
                               kontakt_emails=["Bernd@Muster.de"], projekt="P260050", bestellnummer="B-77",
                               datum="2026-09-24", faellig="2026-10-08", oeffentliche_notiz="Danke.")
    payload = rn["aufrufe"][0][1]
    assert payload["invitations"] == [{"client_contact_id": "k2"}]
    assert payload["project_id"] == "pr1"
    assert payload["custom_value1"] == "P260050" and payload["custom_value2"] == "RB Presse"
    assert (payload["po_number"], payload["date"], payload["due_date"], payload["public_notes"]) == \
        ("B-77", "2026-09-24", "2026-10-08", "Danke.")
    assert payload["line_items"][0]["quantity"] == 2.0 and payload["line_items"][0]["cost"] == 900.0
    assert payload["line_items"][0]["notes"] == "Eigener Text"


def test_anlegen_projekt_per_in_id_und_in_nummer(rn):
    t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "RB-MAVO"}], projekt="pr1")
    t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "RB-MAVO"}], projekt="0007")
    assert [a[1]["project_id"] for a in rn["aufrufe"]] == ["pr1", "pr1"]


def test_anlegen_vkb_wie_normale_position_nichts_automatisch(rn):
    t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "VKBMA"}, {"produkt": "RB-MAVO"}])
    keys = [i["product_key"] for i in rn["aufrufe"][0][1]["line_items"]]
    assert keys == ["VKBMA", "RB-MAVO"]      # Reihenfolge wie übergeben, nicht ans Ende gestellt
    rn["aufrufe"].clear()
    t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "RB-MAVO"}])
    assert [i["product_key"] for i in rn["aufrufe"][0][1]["line_items"]] == ["RB-MAVO"]  # keine VKB angehängt


def test_anlegen_ohne_projekt_rollen_nur_project_id(rn, monkeypatch):
    rollen = {o: dict(r) for o, r in t.K.rollen.items() if o != "rechnung"}
    monkeypatch.setattr(t, "K", dataclasses.replace(t.K, rollen=rollen))
    t.rechnungsentwurf_anlegen("desktop", "70001", [{"produkt": "RB-MAVO"}], projekt="P260050")
    payload = rn["aufrufe"][0][1]
    assert payload["project_id"] == "pr1"
    assert "custom_value1" not in payload and "custom_value2" not in payload


@pytest.mark.parametrize("kwargs, meldung", [
    ({"positionen": [{"produkt": "GIBTSNICHT"}]}, "IN-Katalog nicht"),
    ({"positionen": []}, "mindestens eine Leistung"),
    ({"positionen": [{"produkt": "RB-MAVO", "menge": 0}]}, "Menge"),
    ({"positionen": [{"produkt": "IndLeist"}]}, "Betrag eintragen"),
    ({"kunde": "99999"}, "nicht gefunden"),
    ({"kontakt_emails": ["fremd@example.de"]}, "fremd@example.de"),
    ({"projekt": "P999999"}, "Projekt P999999 nicht gefunden"),
    ({"projekt": "P260051"}, "gehört nicht zu Muster GmbH"),
    ({"datum": "24.09.2026"}, "JJJJ-MM-TT"),
    ({"faellig": "morgen"}, "JJJJ-MM-TT"),
    ({"datum": "2026-09-24", "faellig": "2026-09-23"}, "vor dem Rechnungsdatum"),
])
def test_anlegen_fehler_ohne_schreibaufruf(rn, kwargs, meldung):
    args = {"kunde": "70001", "positionen": [{"produkt": "RB-MAVO"}], **kwargs}
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnungsentwurf_anlegen("desktop", **args)
    assert rn["aufrufe"] == []


# --- rechnungsentwurf_positionen_setzen --------------------------------------------

def test_positionen_setzen_ersetzt_liste(rn):
    rn["invoices"].append(_invoice("RG9990080"))
    text = t.rechnungsentwurf_positionen_setzen("desktop", "rg9990080", [{"produkt": "BAMA"}, {"produkt": "AKAllg"}])
    art, iid, felder = rn["aufrufe"][0]
    assert (art, iid) == ("update_invoice", "iRG9990080")
    assert list(felder) == ["line_items"]
    assert [i["product_key"] for i in felder["line_items"]] == ["BAMA", "AKAllg"]
    assert "2 Positionen" in text and "1000.00 € → 500.00 €" in text and "1190.00 € → 595.00 €" in text
    assert _log_zeile() == "IN-MCP [desktop] rechnungsentwurf_positionen_setzen RG9990080 (2 Positionen)"


@pytest.mark.parametrize("extra, meldung", [
    ({"status_id": "2"}, "versendet, nicht Entwurf"),
    ({"status_id": "3"}, "teilbezahlt, nicht Entwurf"),
    ({"status_id": "4"}, "bezahlt, nicht Entwurf"),
    ({"status_id": "5"}, "storniert, nicht Entwurf"),
    ({"status_id": "6"}, "zurückerstattet, nicht Entwurf"),
    ({"archived_at": 1727000000}, "archiviert"),
])
def test_positionen_setzen_nur_entwurf(rn, extra, meldung):
    rn["invoices"].append(_invoice("RG9990080", **extra))
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnungsentwurf_positionen_setzen("desktop", "RG9990080", [{"produkt": "BAMA"}])
    assert rn["aufrufe"] == []


def test_positionen_setzen_frisch_gelesen_gesperrt(rn, monkeypatch):
    """Die Liste kann veraltet sein - entscheidend ist der frisch gelesene Stand."""
    rn["invoices"].append(_invoice("RG9990080"))
    monkeypatch.setattr(t.nn, "get_invoice", lambda iid: _invoice("RG9990080", status_id="2"))
    with pytest.raises(t.ToolFehler, match="versendet"):
        t.rechnungsentwurf_positionen_setzen("desktop", "RG9990080", [{"produkt": "BAMA"}])
    assert rn["aufrufe"] == []


def test_positionen_setzen_frisch_geloescht(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080"))
    monkeypatch.setattr(t.nn, "get_invoice", lambda iid: _invoice("RG9990080", is_deleted=True))
    with pytest.raises(t.ToolFehler, match="gelöscht"):
        t.rechnungsentwurf_positionen_setzen("desktop", "RG9990080", [{"produkt": "BAMA"}])
    assert rn["aufrufe"] == []


def test_positionen_setzen_fehler_ohne_schreibaufruf(rn):
    rn["invoices"].append(_invoice("RG9990080"))
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.rechnungsentwurf_positionen_setzen("desktop", "RG9999", [{"produkt": "BAMA"}])
    with pytest.raises(t.ToolFehler, match="mindestens eine Leistung"):
        t.rechnungsentwurf_positionen_setzen("desktop", "RG9990080", [])
    assert rn["aufrufe"] == []


# --- rechnungsentwurf_kopf_setzen --------------------------------------------------

def test_kopf_setzen_alle_felder(rn):
    rn["invoices"].append(_invoice("RG9990080"))
    text = t.rechnungsentwurf_kopf_setzen("desktop", "RG9990080", datum="2026-09-24", faellig="2026-10-08",
                                          bestellnummer="B-1", oeffentliche_notiz="", private_notiz="intern")
    assert rn["aufrufe"] == [("update_invoice", "iRG9990080", {
        "date": "2026-09-24", "due_date": "2026-10-08", "po_number": "B-1", "public_notes": "",
        "private_notes": "intern"})]
    assert text.startswith("Rechnung RG9990080:") and "Fälligkeit" in text and "private Notiz" in text
    assert _log_zeile().startswith("IN-MCP [desktop] rechnungsentwurf_kopf_setzen RG9990080 (")


def test_kopf_setzen_nur_datum_passt_zur_bestehenden_faelligkeit(rn):
    rn["invoices"].append(_invoice("RG9990080", date="2026-09-20", due_date="2026-10-04"))
    t.rechnungsentwurf_kopf_setzen("desktop", "RG9990080", datum="2026-10-04")
    assert rn["aufrufe"] == [("update_invoice", "iRG9990080", {"date": "2026-10-04"})]


def test_kopf_setzen_nur_ein_feld(rn):
    rn["invoices"].append(_invoice("RG9990080"))
    t.rechnungsentwurf_kopf_setzen("desktop", "RG9990080", bestellnummer="")
    assert rn["aufrufe"] == [("update_invoice", "iRG9990080", {"po_number": ""})]


def test_kopf_setzen_faellig_gegen_bestehendes_datum(rn):
    rn["invoices"].append(_invoice("RG9990080", date="2026-09-20"))
    with pytest.raises(t.ToolFehler, match="vor dem Rechnungsdatum"):
        t.rechnungsentwurf_kopf_setzen("desktop", "RG9990080", faellig="2026-09-19")
    assert rn["aufrufe"] == []


@pytest.mark.parametrize("kwargs, extra, meldung", [
    ({}, {}, "mindestens eines"),
    ({"datum": "gestern"}, {}, "JJJJ-MM-TT"),
    ({"bestellnummer": "X"}, {"status_id": "2"}, "versendet, nicht Entwurf"),
    ({"bestellnummer": "X"}, {"status_id": "3"}, "teilbezahlt, nicht Entwurf"),
    ({"bestellnummer": "X"}, {"status_id": "5"}, "storniert, nicht Entwurf"),
    ({"bestellnummer": "X"}, {"status_id": "6"}, "zurückerstattet, nicht Entwurf"),
    ({"bestellnummer": "X"}, {"archived_at": 1727000000}, "archiviert"),
    # Punkt 6: ein einzelnes Datum wird gegen das bestehende Gegenstück geprüft
    ({"datum": "2026-10-05"}, {"due_date": "2026-10-04"}, "vor dem Rechnungsdatum"),
    ({"faellig": "2026-09-19"}, {"date": "2026-09-20"}, "vor dem Rechnungsdatum"),
])
def test_kopf_setzen_fehler(rn, kwargs, extra, meldung):
    rn["invoices"].append(_invoice("RG9990080", **extra))
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnungsentwurf_kopf_setzen("desktop", "RG9990080", **kwargs)
    assert rn["aufrufe"] == []


# --- angebot_in_rechnung_umwandeln -------------------------------------------------

@pytest.mark.parametrize("status", ["1", "2", "3"])
def test_umwandeln(rn, status):
    rn["quotes"].append(_quote("AG9990100", status=status))
    text = t.angebot_in_rechnung_umwandeln("desktop", "ag9990100")
    assert rn["aufrufe"] == [("quote_bulk", "convert_to_invoice", ["qAG9990100"])]
    assert "AG9990100" in text and "RG9990090" in text and HINWEIS in text
    assert _log_zeile() == "IN-MCP [desktop] angebot_in_rechnung_umwandeln AG9990100 → RG9990090"


def test_umwandeln_bereits_umgewandelt(rn):
    rn["quotes"].append(_quote("AG9990100", status="4", invoice_id="ialt"))
    rn["invoices"].append(_invoice("RG9990070", id="ialt"))
    with pytest.raises(t.ToolFehler, match="bereits in Rechnung RG9990070 umgewandelt"):
        t.angebot_in_rechnung_umwandeln("desktop", "AG9990100")
    assert rn["aufrufe"] == []


def test_umwandeln_abgelaufen(rn):
    rn["quotes"].append(_quote("AG9990100", status="-1"))
    with pytest.raises(t.ToolFehler, match="abgelaufen – zuerst Gültigkeit verlängern"):
        t.angebot_in_rechnung_umwandeln("desktop", "AG9990100")
    assert rn["aufrufe"] == []


def test_umwandeln_unbekannt(rn):
    with pytest.raises(t.ToolFehler, match="nicht gefunden"):
        t.angebot_in_rechnung_umwandeln("desktop", "AG9999999")
    assert rn["aufrufe"] == []


def test_umwandeln_nicht_bestaetigt_ist_fehler(rn, monkeypatch):
    """Hat das Angebot nach dem Bulk-Aufruf keine Rechnung, gibt es keine Erfolgsmeldung."""
    rn["quotes"].append(_quote("AG9990100"))
    monkeypatch.setattr(t.nn, "quote_bulk", lambda action, ids: rn["aufrufe"].append(("quote_bulk", action, ids)))
    with pytest.raises(t.ToolFehler, match="Umwandlung von Invoice Ninja nicht bestätigt"):
        t.angebot_in_rechnung_umwandeln("desktop", "AG9990100")


def test_umwandeln_rechnung_nicht_lesbar_meldet_erfolg_mit_id(rn, monkeypatch):
    rn["quotes"].append(_quote("AG9990100"))

    def kaputt(iid):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(t.nn, "get_invoice", kaputt)
    text = t.angebot_in_rechnung_umwandeln("desktop", "AG9990100")
    assert "umgewandelt" in text and "iumg" in text and HINWEIS in text


# --- rechnung_als_versendet_markieren ----------------------------------------------

def test_als_versendet_markieren(rn):
    rn["invoices"].append(_invoice("RG9990080"))
    text = t.rechnung_als_versendet_markieren("desktop", "RG9990080")
    assert rn["aufrufe"] == [("invoice_bulk", "mark_sent", ["iRG9990080"])]
    assert "als versendet markiert" in text and "ohne E-Mail" in text
    assert _log_zeile() == "IN-MCP [desktop] rechnung_als_versendet_markieren RG9990080"


def test_als_versendet_nicht_bestaetigt(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080"))
    monkeypatch.setattr(t.nn, "invoice_bulk", lambda action, ids: rn["aufrufe"].append((action, ids)) or [])
    with pytest.raises(t.ToolFehler, match=r"von Invoice Ninja nicht bestätigt \(Status jetzt: Entwurf\)"):
        t.rechnung_als_versendet_markieren("desktop", "RG9990080")


@pytest.mark.parametrize("extra", [{"status_id": "2"}, {"status_id": "4"}, {"archived_at": 1727000000}])
def test_als_versendet_nur_entwurf(rn, extra):
    rn["invoices"].append(_invoice("RG9990080", **extra))
    with pytest.raises(t.ToolFehler):
        t.rechnung_als_versendet_markieren("desktop", "RG9990080")
    assert rn["aufrufe"] == []


# --- rechnung_zahlung_erfassen ------------------------------------------------------

def test_zahlung_default_restbetrag_und_heute(rn):
    rn["invoices"].append(_invoice("RG9990080", status="2", balance=1190.0))
    text = t.rechnung_zahlung_erfassen("desktop", "RG9990080", heute=HEUTE)
    assert rn["aufrufe"] == [("create_payment", {
        "client_id": "c1", "amount": 1190.0, "date": "2026-09-24",
        "invoices": [{"invoice_id": "iRG9990080", "amount": 1190.0}]})]
    assert "1190.00 €" in text and "Restbetrag 0.00 €" in text
    assert _log_zeile() == "IN-MCP [desktop] rechnung_zahlung_erfassen RG9990080 1190.00"


def test_zahlung_teilbetrag_mit_datum_referenz(rn):
    rn["invoices"].append(_invoice("RG9990080", status="3", balance=690.0))
    text = t.rechnung_zahlung_erfassen("desktop", "RG9990080", betrag=200, datum="2026-09-22",
                                       referenz="Überweisung 123", heute=HEUTE)
    assert rn["aufrufe"] == [("create_payment", {
        "client_id": "c1", "amount": 200.0, "date": "2026-09-22", "transaction_reference": "Überweisung 123",
        "invoices": [{"invoice_id": "iRG9990080", "amount": 200.0}]})]
    assert "Restbetrag 490.00 €" in text


@pytest.mark.parametrize("extra, kwargs, meldung", [
    ({"status_id": "1", "balance": 0}, {}, "Entwurf"),
    ({"status_id": "4", "balance": 0}, {}, "bezahlt"),
    ({"status_id": "5", "balance": 0}, {}, "storniert"),
    ({"status_id": "2", "balance": 0}, {}, "keinen offenen Betrag"),
    ({"status_id": "2", "balance": 100}, {"betrag": 100.01}, "höchstens 100.00"),
    ({"status_id": "2", "balance": 100}, {"betrag": 0}, "größer als 0"),
    ({"status_id": "2", "balance": 100}, {"betrag": -5}, "größer als 0"),
    ({"status_id": "2", "balance": 100}, {"betrag": "viel"}, "Zahl"),
    ({"status_id": "2", "balance": 100}, {"betrag": float("nan")}, "Zahl"),
    ({"status_id": "2", "balance": 100}, {"betrag": float("inf")}, "Zahl"),
    ({"status_id": "2", "balance": 100}, {"betrag": 10.005}, "zwei Nachkommastellen"),
    ({"status_id": "2", "balance": 100}, {"datum": "22.09.2026"}, "JJJJ-MM-TT"),
])
def test_zahlung_fehler(rn, extra, kwargs, meldung):
    rn["invoices"].append(_invoice("RG9990080", **extra))
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnung_zahlung_erfassen("desktop", "RG9990080", heute=HEUTE, **kwargs)
    assert rn["aufrufe"] == []


# --- rechnung_versenden ---------------------------------------------------------------

def test_versenden(rn):
    rn["invoices"].append(_invoice("RG9990080", status="2", invitations=[
        {"id": "a", "client_contact_id": "k1"}, {"id": "b", "client_contact_id": "k2"},
        {"id": "c", "client_contact_id": "k3"}]))
    text = t.rechnung_versenden("desktop", "RG9990080")
    assert rn["aufrufe"] == [("invoice_bulk", "email", ["iRG9990080"])]
    assert "an Invoice Ninja zum Versand übergeben an 2 Empfänger (anna@muster.de, bernd@muster.de)" in text
    assert "Zustellung im Verlauf der Rechnung in Invoice Ninja prüfen" in text
    assert _log_zeile() == "IN-MCP [desktop] rechnung_versenden RG9990080 (2 Empfänger)"


def test_versenden_entwurf_erlaubt(rn):
    rn["invoices"].append(_invoice("RG9990080", status="1"))
    t.rechnung_versenden("desktop", "RG9990080")
    assert rn["aufrufe"] == [("invoice_bulk", "email", ["iRG9990080"])]


@pytest.mark.parametrize("extra, meldung", [
    ({"status_id": "5"}, "storniert"),
    ({"status_id": "6"}, "zurückerstattet"),
    ({"invitations": []}, "keine Empfänger"),
    ({"invitations": [{"id": "c", "client_contact_id": "k3"}]}, "keine Empfänger"),
    ({"archived_at": 1727000000}, "archiviert – vor dem Versand in Invoice Ninja wiederherstellen"),
])
def test_versenden_fehler(rn, extra, meldung):
    rn["invoices"].append(_invoice("RG9990080", **extra))
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnung_versenden("desktop", "RG9990080")
    assert rn["aufrufe"] == []


def test_versenden_frisch_geloescht(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080", status="2"))
    monkeypatch.setattr(t.nn, "get_invoice", lambda iid: _invoice("RG9990080", status="2", is_deleted=True))
    with pytest.raises(t.ToolFehler, match="gelöscht"):
        t.rechnung_versenden("desktop", "RG9990080")
    assert rn["aufrufe"] == []


# --- rechnung_stornieren --------------------------------------------------------------

@pytest.mark.parametrize("status", ["2", "3"])
def test_stornieren(rn, status):
    rn["invoices"].append(_invoice("RG9990080", status=status, balance=100.0))
    text = t.rechnung_stornieren("desktop", "RG9990080")
    assert rn["aufrufe"] == [("invoice_bulk", "cancel", ["iRG9990080"])]
    assert "Status storniert in Invoice Ninja; es wird keine Gutschrift/Stornorechnung erzeugt." in text
    assert ("Zahlungen bleiben" in text) is (status == "3")
    assert _log_zeile() == "IN-MCP [desktop] rechnung_stornieren RG9990080"


def test_stornieren_nicht_bestaetigt(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080", status="2"))
    monkeypatch.setattr(t.nn, "invoice_bulk", lambda action, ids: rn["aufrufe"].append((action, ids)) or [])
    with pytest.raises(t.ToolFehler, match=r"von Invoice Ninja nicht bestätigt \(Status jetzt: versendet\)"):
        t.rechnung_stornieren("desktop", "RG9990080")


@pytest.mark.parametrize("status, meldung", [("1", "Entwurf"), ("4", "bezahlt"), ("5", "storniert"),
                                             ("6", "zurückerstattet")])
def test_stornieren_nur_versendet_oder_teilbezahlt(rn, status, meldung):
    rn["invoices"].append(_invoice("RG9990080", status=status))
    with pytest.raises(t.ToolFehler, match=meldung):
        t.rechnung_stornieren("desktop", "RG9990080")
    assert rn["aufrufe"] == []


# --- Server: Registrierung, Hinweise ---------------------------------------------------

RECHNUNGS_TOOLS = {
    "rechnungsentwurf_anlegen": "schreiben", "rechnungsentwurf_positionen_setzen": "schreiben",
    "rechnungsentwurf_kopf_setzen": "schreiben", "angebot_in_rechnung_umwandeln": "schreiben",
    "rechnung_als_versendet_markieren": "status", "rechnung_zahlung_erfassen": "status",
    "rechnung_versenden": "versenden", "rechnung_stornieren": "stornieren"}
# L4: destructiveHint false = kein Effekt nach außen, umkehrbar, keine Stammdaten - siehe
# server.py (NICHT_DESTRUKTIV). rechnungsentwurf_positionen_setzen/-kopf_setzen ändern nur Entwürfe.
NICHT_DESTRUKTIV = {"rechnungsentwurf_anlegen", "rechnungsentwurf_positionen_setzen",
                    "rechnungsentwurf_kopf_setzen", "angebot_in_rechnung_umwandeln"}


def _tools(k):
    pytest.importorskip("fastmcp")
    from in_mcp import server
    return {tool.name: tool for tool in asyncio.run(server.baue_mcp(k).list_tools())}


def test_dss_registriert_alle_rechnungs_tools_mit_hinweisen():
    tools = _tools(t.K)
    assert set(RECHNUNGS_TOOLS) <= set(tools)
    for name in RECHNUNGS_TOOLS:
        a = tools[name].annotations
        assert a.readOnlyHint is False and a.destructiveHint is (name not in NICHT_DESTRUKTIV)


def test_neutral_registriert_kein_rechnungs_tool(neutral):
    assert not set(RECHNUNGS_TOOLS) & set(_tools(t.K))


@pytest.mark.parametrize("recht", ["schreiben", "status", "versenden", "stornieren"])
def test_nur_freigeschaltete_rechte_registriert(neutral, recht):
    k = dataclasses.replace(t.K, rechnungen={r: r == recht for r in ("schreiben", "status", "versenden",
                                                                     "stornieren")})
    registriert = set(RECHNUNGS_TOOLS) & set(_tools(k))
    assert registriert == {n for n, r in RECHNUNGS_TOOLS.items() if r == recht}


def test_rechnungs_tools_neutral_beschrieben(neutral):
    k = dataclasses.replace(t.K, rechnungen={r: True for r in ("schreiben", "status", "versenden", "stornieren")})
    tools = _tools(k)
    for name in RECHNUNGS_TOOLS:
        assert not any(w in tools[name].description for w in ("AG…", "P…", "RG…", "VKBMA", "Termin", "PMS", "DSS"))


def test_anweisungen_rechnungen_je_nach_recht(neutral):
    from in_mcp import server
    assert "Rechnungen:" not in server.anweisungen(t.K)
    alle = dataclasses.replace(t.K, rechnungen={r: True for r in ("schreiben", "status", "versenden", "stornieren")})
    text = server.anweisungen(alle)
    assert "Rechnungen:" in text and "Storno" in text and "nie löschen" in text
    nur_status = dataclasses.replace(t.K, rechnungen={"schreiben": False, "status": True, "versenden": False,
                                                      "stornieren": False})
    text = server.anweisungen(nur_status)
    assert "Zahlungen erfassen" in text and "per E-Mail" not in text and "Entwürfe anlegen" not in text


def _mcp_aufruf(monkeypatch, tool, argumente):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from in_mcp import server
    monkeypatch.setattr(server, "log", MagicMock())
    monkeypatch.setattr(server, "_aufrufer", lambda: "desktop")

    async def aufruf():
        async with Client(server.baue_mcp(t.K)) as c:
            return await c.call_tool(tool, argumente, raise_on_error=False)

    return asyncio.run(aufruf())


def test_server_huelle_uebersetzt_toolfehler(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080", status="1"))
    erg = _mcp_aufruf(monkeypatch, "rechnung_stornieren", {"rechnungsnr": "RG9990080"})
    assert erg.is_error
    assert "Stornieren lassen sich nur versendete oder teilbezahlte Rechnungen" in erg.content[0].text
    assert rn["aufrufe"] == []


def test_server_huelle_erfolg(rn, monkeypatch):
    rn["invoices"].append(_invoice("RG9990080", status="2"))
    erg = _mcp_aufruf(monkeypatch, "rechnung_stornieren", {"rechnungsnr": "RG9990080"})
    assert not erg.is_error and "storniert" in erg.data


def test_versenden_docstring_verspricht_keine_zustellung():
    from in_mcp import server
    doc = server.rechnung_versenden.__doc__
    assert "Standardvorlage" not in doc and "Vorlage wählt Invoice Ninja" in doc


# --- ninja.py: Endpunkte und Header (requests gemockt, kein echtes IN) -------------------

def test_ninja_rechnungs_endpunkte(monkeypatch):
    from in_mcp import ninja
    monkeypatch.setenv("INVOICE_NINJA_URL", "https://in.example.de/")
    monkeypatch.setenv("INVOICE_NINJA_API_TOKEN", "tok")
    aufrufe = []

    def antwort(methode):
        def f(url, headers=None, json=None, params=None, timeout=None):
            aufrufe.append((methode, url, json, params, headers))
            r = MagicMock()
            r.json.return_value = {"data": {"id": "x"}}
            return r
        return f

    for m in ("get", "post", "put"):
        monkeypatch.setattr(ninja.requests, m, antwort(m))
    ninja.get_invoice("i1")
    ninja.create_invoice({"client_id": "c1"})
    ninja.update_invoice("i1", {"po_number": "B"})
    ninja.invoice_bulk("cancel", ["i1"])
    ninja.create_payment({"amount": 1})
    ninja.quote_bulk("convert_to_invoice", ["q1"])
    basis = "https://in.example.de/api/v1"
    assert [(a[0], a[1], a[2]) for a in aufrufe] == [
        ("get", f"{basis}/invoices/i1", None),
        ("post", f"{basis}/invoices", {"client_id": "c1"}),
        ("put", f"{basis}/invoices/i1", {"po_number": "B"}),
        ("post", f"{basis}/invoices/bulk", {"action": "cancel", "ids": ["i1"]}),
        ("post", f"{basis}/payments", {"amount": 1}),
        ("post", f"{basis}/quotes/bulk", {"action": "convert_to_invoice", "ids": ["q1"]})]
    assert aufrufe[0][3] == {"include": "invitations"}
    assert all(a[4]["Accept"] == "application/json" for a in aufrufe[1:])   # Schreibaufrufe

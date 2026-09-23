"""Tests für in_mcp/konfig.py: Laden und Startprüfung der instanz.yaml."""
import re
from pathlib import Path

import pytest

from in_mcp import konfig

BEISPIELE = Path(__file__).resolve().parents[1] / "beispiele"


def test_dss_beispiel_laedt():
    k = konfig.laden(str(BEISPIELE / "instanz.dss.yaml"))
    assert k.name == "DSS-Siegmund"
    assert k.feld("angebot", "bestellt") == "custom_value3"
    assert k.feld("kontakt", "anrede") == "custom_value4"
    assert k.verkaufsbedingungen == ("VKBMA", "AKAllg")
    assert k.standard_verkaufsbedingungen == "VKBMA"
    assert (k.gueltig_standard_tage, k.gueltig_min_tage, k.gueltig_max_tage) == (14, 14, 60)
    assert k.freie_felder("kunde") == ("custom_value2", "custom_value3", "custom_value4")
    assert k.freie_felder("angebot") == ()
    assert "AG…" in k.hinweise


def test_neutral_beispiel_laedt():
    k = konfig.laden(str(BEISPIELE / "instanz.neutral.yaml"))
    assert k.rollen == {}
    assert k.feld("angebot", "bestellt") is None
    assert k.verkaufsbedingungen == () and k.standard_verkaufsbedingungen == ""
    assert k.freie_felder("projekt") == konfig.FELDER


def test_leere_datei_ergibt_neutrale_defaults():
    k = konfig.aus_dict(None)
    assert k.name == "Invoice Ninja" and k.rollen == {}
    assert (k.gueltig_standard_tage, k.gueltig_min_tage, k.gueltig_max_tage) == (30, 1, 365)
    assert k.neue_steuerkategorie == "2"


def test_standard_vkb_ist_erster_eintrag():
    k = konfig.aus_dict({"angebot": {"verkaufsbedingungen": ["AGB"]}})
    assert k.standard_verkaufsbedingungen == "AGB"


@pytest.mark.parametrize("daten, meldung", [
    ({"foo": 1}, "unbekannter Schlüssel foo"),
    ({"instanz": {"nam": "x"}}, "instanz: unbekannter Schlüssel nam"),
    ({"rollen": {"lieferant": {}}}, "rollen: unbekannter Schlüssel lieferant"),
    ({"rollen": {"angebot": {"bestelt": "custom_value3"}}}, "rollen.angebot: unbekannter Schlüssel bestelt"),
    ({"rollen": {"angebot": {"bestellt": "custom_value5"}}}, "rollen.angebot.bestellt: 'custom_value5' ist kein Feld"),
    ({"rollen": {"angebot": {"bestellt": "custom_value3", "abgeschlossen": "custom_value3"}}},
     "rollen.angebot: custom_value3 ist doppelt vergeben"),
    ({"angebot": {"verkaufsbedingungen": ["A"], "standard_verkaufsbedingungen": "B"}},
     "standard_verkaufsbedingungen B steht nicht in verkaufsbedingungen"),
    ({"angebot": {"standard_verkaufsbedingungen": "B"}},
     "standard_verkaufsbedingungen B steht nicht in verkaufsbedingungen"),
    ({"angebot": {"gueltig_min_tage": -1}}, "angebot.gueltig_min_tage: muss eine ganze Zahl ab 0 sein"),
    ({"angebot": {"gueltig_max_tage": "viel"}}, "angebot.gueltig_max_tage: muss eine ganze Zahl ab 0 sein"),
    ({"angebot": {"gueltig_standard_tage": 70, "gueltig_max_tage": 60}},
     "gueltig_standard_tage muss zwischen gueltig_min_tage und gueltig_max_tage liegen"),
    ({"angebot": {"angebotsnr_im_projektnamen": "AG(\\d+"}}, "ungültiger regulärer Ausdruck"),
    ({"produkt": {"neue_steuerkategorie": "7"}}, "produkt.neue_steuerkategorie: erlaubt sind 1, 2, 3"),
    ({"rollen": ["kunde"]}, "rollen: muss ein Abschnitt mit Schlüsseln sein"),
    ({"angebot": {"verkaufsbedingungen": "VKBMA"}},
     "angebot.verkaufsbedingungen: muss eine Liste sein, z. B. [VKBMA]."),
])
def test_startpruefung(daten, meldung):
    with pytest.raises(konfig.KonfigFehler, match=re.escape(meldung)):
        konfig.aus_dict(daten)


def test_laden_fehlende_datei(tmp_path):
    with pytest.raises(konfig.KonfigFehler, match="fehlt"):
        konfig.laden(str(tmp_path / "gibtsnicht.yaml"))


def test_laden_kaputtes_yaml(tmp_path):
    datei = tmp_path / "x.yaml"
    datei.write_text("rollen: [\n", encoding="utf-8")
    with pytest.raises(konfig.KonfigFehler, match="kein gültiges YAML"):
        konfig.laden(str(datei))

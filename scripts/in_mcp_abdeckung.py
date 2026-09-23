"""Abdeckungs-Prüfskript für den IN-MCP: welche befüllten IN-Felder geben die Tools (noch) nicht aus.

Nur lesende GETs gegen das echte Invoice Ninja. Druckt ausschließlich Feldnamen und Anzahlen,
nie Werte. Aufruf (im Container dss-in-mcp):

    docker exec dss-in-mcp python scripts/in_mcp_abdeckung.py

Stand 23.09.2026: GEDECKT bildet ab, was in_mcp/tools.py tatsächlich ausgibt (dort nachlesen,
wenn sich das Tool-Mapping ändert).
"""
import requests

from in_mcp import ninja as nn
from in_mcp.tools import SENSIBEL, TECHNIK

url, token = nn._get_config()
H = {"X-API-Token": token}


def roh(pfad, **p):
    p.setdefault("per_page", 500)
    r = requests.get(f"{url}/api/v1/{pfad}", headers=H, params=p, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


# Felder, die die MCP-Tools heute ausgeben (aus in_mcp/tools.py abgelesen)
GEDECKT = {
    "Kunde": {"id", "number", "name", "city", "address1", "address2", "postal_code", "vat_number",
              "phone", "website", "public_notes", "private_notes", "contacts", "custom_value1",
              "custom_value2", "custom_value3", "custom_value4",
              "state", "shipping_address1", "shipping_address2", "shipping_postal_code",
              "shipping_city", "shipping_state", "paid_to_date", "balance", "payment_balance",
              "credit_balance"},
    "Kontakt": {"id", "first_name", "last_name", "email", "phone", "custom_value1", "custom_value2",
                "custom_value3", "custom_value4"},
    "Angebot": {"number", "client", "client_id", "custom_value1", "custom_value2", "custom_value3",
                "custom_value4", "date", "due_date", "status_id", "archived_at", "po_number", "amount",
                "total_taxes", "line_items", "private_notes", "public_notes", "id", "is_deleted",
                "invoice_id", "discount", "is_amount_discount", "tax_name1", "tax_rate1"},
    "Position": {"product_key", "notes", "quantity", "cost", "tax_rate1", "line_total",
                 "gross_line_total", "tax_amount", "tax_name1"},
    "Projekt": {"id", "name", "custom_value1", "custom_value2", "custom_value3", "custom_value4",
                "archived_at", "client", "client_id", "is_deleted", "number", "due_date",
                "private_notes", "public_notes", "task_rate"},
    "Rechnung": {"number", "client", "client_id", "date", "due_date", "amount", "balance", "status_id",
                 "is_deleted", "po_number", "custom_value1", "custom_value2", "custom_value3",
                 "custom_value4", "total_taxes",
                 "paid_to_date", "line_items", "private_notes", "discount", "is_amount_discount", "id"},
    "Produkt": {"product_key", "notes", "price", "tax_rate1", "tax_name1", "tax_id", "is_deleted",
                "archived_at"},
    "Zahlung": {"id", "number", "date", "amount", "client", "client_id", "transaction_reference",
                "status_id", "invoices", "is_deleted", "paymentables"},
    "Lieferant": {"id", "name", "number", "address1", "postal_code", "city", "phone", "website",
                  "vat_number", "contacts", "is_deleted"},
    "Lieferant-Kontakt": {"first_name", "last_name", "email", "phone"},
}

# Reine Technik/sensible Felder ohne Aussagewert für den Anwender - aus in_mcp_tools.py übernommen,
# damit das Prüfskript und in_rohdaten dieselbe Definition verwenden
UNINTERESSANT = TECHNIK | SENSIBEL


def befuellt(obj):
    def voll(v):
        return v not in (None, "", 0, "0", 0.0, [], {}, False, "0.00")
    return {k for k, v in obj.items() if voll(v)}


def auswerten(name, objekte):
    zaehler = {}
    for o in objekte:
        for f in befuellt(o):
            zaehler[f] = zaehler.get(f, 0) + 1
    fehlt = {f: n for f, n in zaehler.items() if f not in GEDECKT[name] and f not in UNINTERESSANT}
    print(f"\n== {name}: {len(objekte)} Datensätze, befüllte Felder ohne MCP-Ausgabe ==")
    if not fehlt:
        print("   (keine)")
    for f, n in sorted(fehlt.items(), key=lambda x: -x[1]):
        print(f"   {f:28s} in {n:4d} Datensätzen")


clients = roh("clients", status="active")
auswerten("Kunde", clients)
auswerten("Kontakt", [c for cl in clients for c in cl.get("contacts", [])])

quotes = [q for q in roh("quotes", include="client", status="active,archived") if not q.get("is_deleted")]
auswerten("Angebot", quotes)
auswerten("Position", [i for q in quotes for i in q.get("line_items", [])])

auswerten("Projekt", roh("projects", include="client", status="active,archived"))

invoices = [i for i in roh("invoices", include="client", status="active,archived") if not i.get("is_deleted")]
auswerten("Rechnung", invoices)

auswerten("Produkt", roh("products"))

payments = [p for p in roh("payments", include="client,invoices,paymentables", status="active,archived")
           if not p.get("is_deleted")]
auswerten("Zahlung", payments)

vendors = [v for v in roh("vendors", status="active,archived") if not v.get("is_deleted")]
auswerten("Lieferant", vendors)
auswerten("Lieferant-Kontakt", [c for v in vendors for c in v.get("contacts", [])])

try:
    comp = roh("companies")
    cf = comp[0].get("custom_fields", {}) if comp else {}
    print("\n== Beschriftungen der Custom Fields in IN ==")
    for k in sorted(cf):
        if cf[k]:
            print(f"   {k:12s} = {cf[k]}")
except Exception as e:
    print("Custom-Field-Beschriftungen nicht lesbar:", e)

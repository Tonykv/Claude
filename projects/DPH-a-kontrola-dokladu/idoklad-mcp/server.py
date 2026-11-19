"""
iDoklad MCP server – kontrola dokladů a náhled přiznání k DPH.

Pouze ČTE data z iDoklad API v3 (žádné zápisy).

Nástroje:
  - kontrola_prijatych_faktur(obdobi)  – duplicity (VS + externí číslo + částka),
                                          chybějící členění DPH na řádcích,
                                          datum pořízení dokladu = dnešní datum
  - nahled_priznani_dph(obdobi)        – přijaté faktury (dle data přijetí), přijaté účtenky
                                          (dle DateOfIssue) + vydané (dle DUZP),
                                          součet DPH: přijaté a účtenky +, vydané ×(−1)
  - idoklad_get(path, params)          – obecné čtení libovolného endpointu (diagnostika)

Spuštění:
  python server.py                 # stdio – pro Claude Desktop
  python server.py --http          # Streamable HTTP – pro vzdálený konektor v claude.ai

Proměnné prostředí:
  IDOKLAD_CLIENT_ID, IDOKLAD_CLIENT_SECRET   (povinné)
  MCP_SECRET_PATH   – tajná část URL pro HTTP režim (doporučeno), např. 8f3k...;
                      server pak poslouchá na /<MCP_SECRET_PATH>/mcp
  PORT              – port pro HTTP režim (výchozí 8000)
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

TOKEN_URL = "https://identity.idoklad.cz/server/connect/token"
API_URL = "https://api.idoklad.cz/v3"
PAGE_SIZE = 100

# Názvy polí v iDoklad API v3. Pokud by se u tvého účtu jmenovala jinak,
# stačí upravit tady (nebo si je ověřit nástrojem idoklad_get).
F = {
    "received_date_filter": "DateOfReceiving",   # datum přijetí (přijaté faktury)
    "issued_date_filter": "DateOfTaxing",        # DUZP (vydané faktury)
    "receipt_date_filter": "DateOfIssue",        # datum dokladu (přijaté účtenky)
    "doc_number": ["DocumentNumber"],
    "vs": ["VariableSymbol"],
    "external_number": ["ReceivedDocumentNumber", "OriginalDocumentNumber", "ExternalDocumentNumber"],
    "description": ["Description"],
    "partner": ["PartnerAddress.NickName", "PartnerName", "Partner.CompanyName"],
    "date_issue": ["DateOfIssue"],
    # datum pořízení = kdy byl záznam v iDokladu založen (název pole ověř přes idoklad_get)
    "date_created": ["Metadata.DateCreated", "Metadata.CreatedDate", "DateCreated",
                     "DateOfCreation", "CreatedDate", "Created"],
    "date_receiving": ["DateOfReceiving"],
    "date_taxing": ["DateOfTaxing"],
    "currency": ["CurrencyCode", "Currency.Code"],
    # částky v domácí měně (Hc) mají přednost – DPH se přiznává v CZK
    "total_without_vat": ["Prices.TotalWithoutVatHc", "Prices.TotalWithoutVat", "TotalWithoutVatHc", "TotalWithoutVat"],
    "total_vat": ["Prices.TotalVatHc", "Prices.TotalVat", "TotalVatHc", "TotalVat"],
    "total_with_vat": ["Prices.TotalWithVatHc", "Prices.TotalWithVat", "TotalWithVatHc", "TotalWithVat"],
    # řádky
    "items": ["Items"],
    "item_name": ["Name"],
    "item_vat_code": ["VatCodeId", "VatClassificationId", "VatCode.Id", "VatCode"],
    "item_type": ["ItemType"],
    "item_total": ["Prices.TotalWithVat", "Prices.TotalWithVatHc", "TotalWithVat", "Amount"],
}

# Typy řádků, u kterých se členění DPH nevyžaduje (zaokrouhlení apod.)
ITEM_TYPES_WITHOUT_VAT_CODE = {1, "ItemTypeRound", "Round"}


# --------------------------------------------------------------------------- #
# Pomocné funkce
# --------------------------------------------------------------------------- #

def get_field(obj: dict, candidates: list[str], default: Any = None) -> Any:
    """Vrátí první nalezené pole ze seznamu kandidátů (podporuje tečkovou notaci)."""
    for path in candidates:
        cur: Any = obj
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default


def dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def day(value: Any) -> str | None:
    """'2026-07-15T00:00:00' -> '2026-07-15'"""
    if not value:
        return None
    return str(value)[:10]


def parse_quarter(text: str) -> tuple[date, date, str]:
    """Rozpozná čtvrtletí z textu: 'Q3 2026', '2026-Q3', '3/2026', '3. čtvrtletí 2026'."""
    t = text.strip().lower()
    year_m = re.search(r"(20\d{2})", t)
    if not year_m:
        raise ValueError(f"Nerozpoznán rok v '{text}'. Použij např. 'Q3 2026'.")
    year = int(year_m.group(1))
    rest = t[: year_m.start()] + " " + t[year_m.end():]
    q_m = (re.search(r"q\s*([1-4])", rest) or re.search(r"([1-4])\s*q", rest)
           or re.search(r"(?<!\d)([1-4])(?!\d)", rest))
    if not q_m:
        raise ValueError(f"Nerozpoznáno čtvrtletí v '{text}'. Použij např. 'Q3 2026'.")
    q = int(q_m.group(1))
    start = date(year, 3 * q - 2, 1)
    end = date(year, 3 * q, 31 if 3 * q in (3, 12) else 30)
    return start, end, f"{q}. čtvrtletí {year}"


# --------------------------------------------------------------------------- #
# iDoklad klient
# --------------------------------------------------------------------------- #

class IDokladClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_exp = 0.0
        self._http = httpx.Client(timeout=60)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "idoklad_api",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"Přihlášení do iDokladu selhalo ({r.status_code}): {r.text[:300]}")
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def get(self, path: str, params: dict | None = None) -> Any:
        r = self._http.get(
            f"{API_URL}/{path.lstrip('/')}",
            params=params or {},
            headers={"Authorization": f"Bearer {self._get_token()}", "Accept-Language": "cs-CZ"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"iDoklad GET {path} selhal ({r.status_code}): {r.text[:300]}")
        return r.json()

    def list_all(self, path: str, date_field: str, start: date, end: date) -> list[dict]:
        """Stáhne všechny stránky seznamu dokladů s filtrem na datum (včetně)."""
        flt = f"({date_field}~gte~{start.isoformat()})~and~({date_field}~lte~{end.isoformat()})"
        out: list[dict] = []
        page = 1
        while True:
            resp = self.get(path, {"filter": flt, "page": page, "pagesize": PAGE_SIZE})
            data = resp.get("Data", resp) if isinstance(resp, dict) else resp
            items = data.get("Items", []) if isinstance(data, dict) else data
            out.extend(items)
            total_pages = data.get("TotalPages", 1) if isinstance(data, dict) else 1
            if page >= (total_pages or 1) or not items:
                break
            page += 1
        # pojistka: filtr znovu aplikujeme i lokálně
        s, e = start.isoformat(), end.isoformat()
        return [d for d in out if (dd := day(d.get(date_field))) is None or s <= dd <= e]

    def ensure_items(self, path: str, doc: dict) -> dict:
        """Seznamy nemusí vracet řádky – v tom případě dotáhne detail dokladu."""
        if get_field(doc, F["items"]) is None and doc.get("Id") is not None:
            detail = self.get(f"{path}/{doc['Id']}")
            return detail.get("Data", detail) if isinstance(detail, dict) else doc
        return doc


# --------------------------------------------------------------------------- #
# Byznys logika (čisté funkce – testovatelné bez API)
# --------------------------------------------------------------------------- #

def summarize_receipt(doc: dict) -> dict:
    """Přijatá účtenka – rozhoduje datum dokladu (DateOfIssue)."""
    return {
        "id": doc.get("Id"),
        "cislo_dokladu": get_field(doc, F["doc_number"]),
        "externi_cislo": get_field(doc, F["external_number"]),
        "partner": get_field(doc, F["partner"]),
        "popis": get_field(doc, F["description"]),
        "datum_dokladu": day(get_field(doc, F["date_issue"])),
        "bez_dph": money(dec(get_field(doc, F["total_without_vat"]))),
        "dph": money(dec(get_field(doc, F["total_vat"]))),
        "celkem": money(dec(get_field(doc, F["total_with_vat"]))),
    }


def summarize_doc(doc: dict, kind: str) -> dict:
    return {
        "id": doc.get("Id"),
        "cislo_dokladu": get_field(doc, F["doc_number"]),
        "vs": get_field(doc, F["vs"]),
        "externi_cislo": get_field(doc, F["external_number"]) if kind == "prijata" else None,
        "partner": get_field(doc, F["partner"]),
        "popis": get_field(doc, F["description"]),
        "datum_prijeti": day(get_field(doc, F["date_receiving"])) if kind == "prijata" else None,
        "duzp": day(get_field(doc, F["date_taxing"])),
        "mena": get_field(doc, F["currency"]),
        "bez_dph": money(dec(get_field(doc, F["total_without_vat"]))),
        "dph": money(dec(get_field(doc, F["total_vat"]))),
        "celkem": money(dec(get_field(doc, F["total_with_vat"]))),
    }


def find_duplicates(rows: list[dict]) -> list[dict]:
    """Duplicita = stejný VS + stejné externí číslo + stejná celková částka."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (
            (r["vs"] or "").strip(),
            (r["externi_cislo"] or "").strip().upper(),
            r["celkem"],
        )
        groups[key].append(r)
    dups = []
    for (vs, ext, total), items in groups.items():
        if len(items) > 1:
            dups.append({
                "vs": vs, "externi_cislo": ext, "celkem": total,
                "pocet": len(items),
                "doklady": [{"id": i["id"], "cislo_dokladu": i["cislo_dokladu"],
                             "partner": i["partner"], "datum_prijeti": i["datum_prijeti"]} for i in items],
            })
    return dups


def missing_vat_codes(doc: dict) -> list[dict]:
    """Řádky faktury bez vyplněného členění DPH (ignoruje zaokrouhlení a nulové řádky)."""
    missing = []
    for idx, item in enumerate(get_field(doc, F["items"], []) or [], start=1):
        if get_field(item, F["item_type"]) in ITEM_TYPES_WITHOUT_VAT_CODE:
            continue
        if dec(get_field(item, F["item_total"])) == 0:
            continue
        code = get_field(item, F["item_vat_code"])
        if code in (None, "", 0):
            missing.append({"radek": idx, "nazev": get_field(item, F["item_name"])})
    return missing


def check_today(doc: dict, today: date) -> str | None:
    """'dnes' = doklad byl pořízen dnes, 'nezjisteno' = pole s datem pořízení chybí, None = OK."""
    created = day(get_field(doc, F["date_created"]))
    if created is None:
        return "nezjisteno"
    return "dnes" if created == today.isoformat() else None


def build_control(received_docs: list[dict], label: str, today: date) -> dict:
    rows = [summarize_doc(d, "prijata") for d in received_docs]
    dups = find_duplicates(rows)
    no_vat = []
    today_hits = []
    created_unknown = 0
    for d, r in zip(received_docs, rows):
        if (m := missing_vat_codes(d)):
            no_vat.append({"cislo_dokladu": r["cislo_dokladu"], "vs": r["vs"],
                           "partner": r["partner"], "radky_bez_cleneni": m})
        h = check_today(d, today)
        if h == "dnes":
            today_hits.append({"cislo_dokladu": r["cislo_dokladu"], "vs": r["vs"],
                               "partner": r["partner"], "datum_porizeni": today.isoformat()})
        elif h == "nezjisteno":
            created_unknown += 1
    ok = not dups and not no_vat and not today_hits and not created_unknown
    return {
        "obdobi": label,
        "pocet_prijatych_faktur": len(rows),
        "vysledek": "OK – bez nálezů" if ok else "Nalezeny problémy",
        "duplicity": dups,
        "chybi_cleneni_dph": no_vat,
        "porizeno_dnes": today_hits,
        "datum_porizeni_nezjisteno": (
            f"U {created_unknown} dokladů chybí datum pořízení – ověř název pole "
            "přes idoklad_get a doplň ho do F['date_created'] v server.py."
            if created_unknown else None),
        "faktury": rows,
    }


def _section(rows: list[dict], kriterium: str) -> dict:
    return {
        "kriterium": kriterium,
        "pocet": len(rows),
        "soucet_bez_dph": money(sum((dec(r["bez_dph"]) for r in rows), Decimal("0"))),
        "soucet_dph": money(sum((dec(r["dph"]) for r in rows), Decimal("0"))),
        "soucet_celkem": money(sum((dec(r["celkem"]) for r in rows), Decimal("0"))),
        "polozky": rows,
    }


def build_preview(received_docs: list[dict], issued_docs: list[dict], label: str,
                  receipt_docs: list[dict] | None = None) -> dict:
    rec = [summarize_doc(d, "prijata") for d in received_docs]
    iss = [summarize_doc(d, "vydana") for d in issued_docs]
    rcp = [summarize_receipt(d) for d in (receipt_docs or [])]
    rec_vat = sum((dec(r["dph"]) for r in rec), Decimal("0"))
    rcp_vat = sum((dec(r["dph"]) for r in rcp), Decimal("0"))
    iss_vat = sum((dec(r["dph"]) for r in iss), Decimal("0"))
    saldo = rec_vat + rcp_vat + (iss_vat * -1)
    return {
        "obdobi": label,
        "prijate_faktury": _section(rec, "datum přijetí v období"),
        "prijate_uctenky": _section(rcp, "datum dokladu (DateOfIssue) v období"),
        "vydane_faktury": _section(iss, "DUZP v období"),
        "vypocet_dph": {
            "dph_prijate": money(rec_vat),
            "dph_prijate_uctenky": money(rcp_vat),
            "dph_vydane_krat_minus_1": money(iss_vat * -1),
            "saldo": money(saldo),
            "vyklad": ("Záporné saldo = vlastní daňová povinnost (k úhradě)"
                       if saldo < 0 else "Kladné saldo = nadměrný odpočet"
                       if saldo > 0 else "Saldo je nulové"),
        },
        "poznamka": "Dobropisy, prodejky a pokladní doklady nejsou zahrnuty. "
                    "Saldo = DPH přijatých faktur + DPH přijatých účtenek + DPH vydaných × (−1).",
    }


# --------------------------------------------------------------------------- #
# MCP server
# --------------------------------------------------------------------------- #

mcp = FastMCP("idoklad-dph")
_client: IDokladClient | None = None


def client() -> IDokladClient:
    global _client
    if _client is None:
        cid, sec = os.environ.get("IDOKLAD_CLIENT_ID"), os.environ.get("IDOKLAD_CLIENT_SECRET")
        if not cid or not sec:
            raise RuntimeError("Chybí IDOKLAD_CLIENT_ID nebo IDOKLAD_CLIENT_SECRET.")
        _client = IDokladClient(cid, sec)
    return _client


def _received(start: date, end: date) -> list[dict]:
    c = client()
    docs = c.list_all("ReceivedInvoices", F["received_date_filter"], start, end)
    return [c.ensure_items("ReceivedInvoices", d) for d in docs]


@mcp.tool()
def kontrola_prijatych_faktur(obdobi: str) -> dict:
    """Kontrola přijatých faktur za čtvrtletí DPH (podle data přijetí).

    Hledá duplicity (stejný VS + externí číslo + částka), řádky bez členění DPH
    a doklady pořízené (založené v iDokladu) dnes.
    obdobi: např. 'Q3 2026', '3/2026' nebo '3. čtvrtletí 2026'.
    """
    start, end, label = parse_quarter(obdobi)
    return build_control(_received(start, end), label, date.today())


@mcp.tool()
def nahled_priznani_dph(obdobi: str) -> dict:
    """Náhled přiznání k DPH za čtvrtletí.

    Přijaté faktury podle data přijetí, přijaté účtenky podle data dokladu (DateOfIssue),
    vydané faktury podle DUZP; u každé číslo, VS/datum, popis, bez DPH, DPH a celkem.
    Saldo DPH = DPH přijatých faktur + DPH přijatých účtenek + DPH vydaných × (−1).
    obdobi: např. 'Q3 2026', '3/2026' nebo '3. čtvrtletí 2026'.
    """
    start, end, label = parse_quarter(obdobi)
    c = client()
    issued = c.list_all("IssuedInvoices", F["issued_date_filter"], start, end)
    receipts = c.list_all("ReceivedReceipts", F["receipt_date_filter"], start, end)
    return build_preview(_received(start, end), issued, label, receipts)


@mcp.tool()
def idoklad_get(path: str, filter: str = "", page: int = 1, pagesize: int = 20) -> Any:
    """Obecné čtení z iDoklad API v3 (jen GET), např. path='ReceivedInvoices'
    nebo 'ReceivedInvoices/123'. Slouží k ověření názvů polí a diagnostice.
    filter ve formátu iDokladu, např. '(DateOfReceiving~gte~2026-07-01)'."""
    params: dict[str, Any] = {"page": page, "pagesize": min(pagesize, 200)}
    if filter:
        params["filter"] = filter
    return client().get(path, params)


if __name__ == "__main__":
    if "--http" in sys.argv:
        secret = os.environ.get("MCP_SECRET_PATH", "").strip("/")
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.settings.streamable_http_path = f"/{secret}/mcp" if secret else "/mcp"
        # Veřejný hostname (např. Azure) musí projít ochranou proti DNS rebindingu.
        from mcp.server.transport_security import TransportSecuritySettings
        hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
        mcp.settings.transport_security = (
            TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                      allowed_hosts=hosts + ["localhost:*", "127.0.0.1:*"])
            if hosts else TransportSecuritySettings(enable_dns_rebinding_protection=False)
        )
        if not secret:
            print("VAROVÁNÍ: MCP_SECRET_PATH není nastaven – endpoint je bez ochrany.", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()

# iDoklad MCP server – kontrola dokladů a náhled DPH

MCP server, který Claude zpřístupní data z iDokladu (API v3). Server **jen čte**, nic v iDokladu nemění.

## Nástroje

| Nástroj | Co dělá |
|---|---|
| `kontrola_prijatych_faktur(obdobi)` | Přijaté faktury podle **data přijetí** v daném čtvrtletí. Hledá duplicity (stejný VS + externí číslo + celková částka), řádky bez **členění DPH** a doklady s **datem pořízení** (založení v iDokladu) rovným dnešku. |
| `nahled_priznani_dph(obdobi)` | Přijaté faktury (datum přijetí), přijaté účtenky (**DateOfIssue**) a vydané faktury (**DUZP**): číslo, VS / datum, popis, bez DPH, DPH, celkem. Saldo = DPH přijatých faktur + DPH přijatých účtenek + DPH vydaných × (−1). Záporné saldo znamená daň k úhradě. |
| `idoklad_get(path, filter)` | Obecné čtení z API, slouží k diagnostice a ověření názvů polí. |

Období lze zadat jako `Q3 2026`, `2026-Q3`, `3/2026` nebo `3. čtvrtletí 2026`.

Částky se berou v domácí měně (CZK). Dobropisy, prodejky a pokladní doklady zatím zahrnuty nejsou.

## 1. Přístup do iDokladu

V iDokladu v nastavení API vygeneruj **Client ID** a **Client Secret**. Server se přihlašuje metodou *client credentials* (`scope=idoklad_api`).

## 2a. Lokálně v Claude Desktop

```bash
cd idoklad-mcp
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Do `claude_desktop_config.json` (Claude Desktop → Nastavení → sekce pro vývojáře → upravit konfiguraci) přidej:

```json
{
  "mcpServers": {
    "idoklad": {
      "command": "C:\\cesta\\k\\idoklad-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\cesta\\k\\idoklad-mcp\\server.py"],
      "env": {
        "IDOKLAD_CLIENT_ID": "tvoje-client-id",
        "IDOKLAD_CLIENT_SECRET": "tvuj-client-secret"
      }
    }
  }
}
```

Na macOS/Linuxu použij cestu `.venv/bin/python`. Claude Desktop pak restartuj.

## 2b. Vzdálený konektor v claude.ai (Azure Container Apps)

```bash
az containerapp up \
  --name idoklad-mcp --resource-group rg-idoklad --location westeurope \
  --source . --ingress external --target-port 8000 \
  --env-vars IDOKLAD_CLIENT_ID=... IDOKLAD_CLIENT_SECRET=... \
             MCP_SECRET_PATH=$(openssl rand -hex 24)
```

Volitelně nastav i `MCP_ALLOWED_HOSTS=<hostname aplikace>`, aby server přijímal požadavky jen na svůj hostname.

V claude.ai pak v Konektorech zvol „+“ → „Add custom connector“ a vlož URL:

```
https://<hostname-aplikace>/<MCP_SECRET_PATH>/mcp
```

Tajná část URL funguje jako heslo. Nikomu ji neposílej. Secrety je lepší uložit jako *secrets* v Container Apps než jako běžné proměnné.

## 3. První spuštění – ověření polí

Při prvním použití požádej Claude: *„Zavolej idoklad_get na ReceivedInvoices s pagesize 1.“* Ověř, že pole odpovídají slovníku `F` na začátku `server.py`. Jde hlavně o `ReceivedDocumentNumber` (externí číslo), `VatCodeId` (členění DPH), `Prices.TotalVatHc` (DPH) a pole s datem pořízení (`F["date_created"]`, hledá se např. `Metadata.DateCreated`). Pokud se jmenují jinak, uprav je tam.

## Použití v projektu

> Zkontroluj přijaté faktury za Q3 2026 a ukaž náhled přiznání k DPH.

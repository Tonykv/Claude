# DPH a kontrola dokladů

Claude projekt pro čtvrtletní přiznání k DPH s daty z iDokladu.

## Co projekt dělá

**Kontrola přijatých faktur za čtvrtletí** (podle data přijetí):
- duplicity – stejný variabilní symbol, externí číslo a částka,
- vyplněné členění DPH u každého řádku faktury,
- datum pořízení dokladu není dnešní datum.

**Náhled přiznání k DPH:**
- přijaté faktury podle data přijetí – VS, popis, bez DPH, DPH, celkem,
- vydané faktury podle DUZP – číslo, VS, popis, bez DPH, DPH, celkem,
- saldo DPH = DPH přijatých + DPH vydaných × (−1).

## Obsah

| Složka | Popis |
|---|---|
| [`idoklad-mcp/`](idoklad-mcp/) | Lokální MCP server pro Claude Desktop, který čte data z iDoklad API v3. Návod k instalaci je v [README](idoklad-mcp/README.md). |

## Použití

V chatu projektu v Claude Desktop napiš například:

> Zkontroluj přijaté faktury za Q3 2026 a ukaž náhled přiznání k DPH.

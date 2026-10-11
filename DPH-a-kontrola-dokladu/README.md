# DPH a kontrola dokladů

Claude projekt pro čtvrtletní přiznání k DPH s daty z iDokladu.

## Co projekt dělá

**Kontrola přijatých faktur za čtvrtletí** (podle data přijetí). Každý nález je chyba k opravě:
- duplicity – stejný variabilní symbol, externí číslo a celková částka,
- vyplněné členění DPH u každého řádku faktury,
- datum pořízení dokladu není dnešní datum.

**Náhled přiznání k DPH:**
- přijaté faktury podle data přijetí – VS, popis, bez DPH, DPH, celkem,
- přijaté účtenky podle data dokladu (DateOfIssue) – datum, popis, bez DPH, DPH, celkem,
- vydané faktury podle DUZP – číslo, VS, popis, bez DPH, DPH, celkem,
- saldo DPH = DPH přijatých faktur + DPH přijatých účtenek + DPH vydaných faktur × (−1).

Záporné saldo znamená daň k úhradě, kladné nadměrný odpočet.

**Omezení:** částky jsou v domácí měně (CZK). Dobropisy, prodejky a pokladní doklady zatím zahrnuty nejsou.

## Obsah

| Složka | Popis |
|---|---|
| [`idoklad-mcp/`](idoklad-mcp/) | Lokální MCP server pro Claude Desktop, který čte data z iDoklad API v3. Návod k instalaci je v [README](idoklad-mcp/README.md). |

## Použití

Postup kontroly a náhledu je uložený jako skill **idoklad-dph**, ne v instrukcích projektu. Skill se načte jen tehdy, když ho potřebuješ, takže běžné chaty v projektu nezatěžuje.

1. Ulož skill `idoklad-dph` v claude.ai.
2. Pole Instructions v projektu nech prázdné.
3. Server iDoklad zapni v nabídce nástrojů jen v chatech, kde kontroluješ doklady nebo DPH.

V takovém chatu v Claude Desktop pak napiš `/idoklad-dph` nebo třeba:

> Zkontroluj přijaté faktury za Q3 2026 a ukaž náhled přiznání k DPH.

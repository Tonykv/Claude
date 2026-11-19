# Claude

Repozitář projektů pro Claude (Claude Desktop, Claude Code). Každý projekt má vlastní složku ve [`projects/`](projects/) s vlastním README.

## Projekty

| Složka | Popis |
|---|---|
| [`projects/DPH-a-kontrola-dokladu/`](projects/DPH-a-kontrola-dokladu/) | Čtvrtletní kontrola přijatých faktur a náhled přiznání k DPH z iDokladu. Obsahuje lokální MCP server [`idoklad-mcp`](projects/DPH-a-kontrola-dokladu/idoklad-mcp/). |
| [`projects/garmin-mcp/`](projects/garmin-mcp/) | MCP server, který zpřístupňuje data o váze z Garmin Health API. |
| [`projects/cv/`](projects/cv/) | Verze životopisu ve formátu PDF (grid a career timeline). |

## Skills pro Claude Code

| Složka | Popis |
|---|---|
| [`.claude/skills/huashu-design/`](.claude/skills/huashu-design/) | Skill pro design, prezentace a video (převzatý, licence MIT). Musí zůstat v `.claude/skills/`, aby ho Claude Code načetl. |

## Konvence

- Nový projekt = nová složka v `projects/` s vlastním `README.md`.
- Tajné údaje (`.env`, `claude_desktop_config.json`) se necommitují, viz [`.gitignore`](.gitignore).

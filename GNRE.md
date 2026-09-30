# Lançamento de GNRE no ERP — Fluxo Completo

## Visão Geral

Automação para ler PDFs de GNRE (Guia Nacional de Recolhimento de Tributos Estaduais), extrair os dados e lançar o título no ERP ADMSIS.

---

## Dados Extraídos do PDF

| Campo | Origem no PDF | Exemplo |
|-------|---------------|---------|
| **UF Favorecida** | Linha após "Guia Nacional de Recolhimento..." | `DF` |
| **Fornecedor** | Mapeado conforme UF | `SECRETARIA DA FAZENDA - GOV. DO ESTADO DO DISTRITO FEDERAL` |
| **Filial** | 1º número da linha após "Razão Social" | `551` |
| **Valor** | "Valor Principal R$ XXX,XX" | `483,86` |
| **Vencimento** | "Data de Vencimento" ou "Documento Válido para pagamento" | `01/07/2026` |
| **Nº Documento** | Final da linha do Telefone | `29014` |

## Mapeamento UF → Fornecedor (completo - 27 UFs)

Mapeamento completo em `src/pdf_parser.py` — variável `UF_FAVORECIDA_MAP`.

| UF | Fornecedor no ERP |
|----|-------------------|
| AC | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO ACRE |
| AL | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE ALAGOAS |
| AP | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO AMAPA |
| AM | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO AMAZONAS |
| BA | SECRETARIA DA FAZENDA - GOV. DO ESTADO DA BAHIA |
| CE | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO CEARA |
| DF | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO DISTRITO FEDERAL |
| ES | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO ESPIRITO SANTO |
| GO | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE GOIAS |
| MA | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO MARANHAO |
| MT | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MATO GROSSO |
| MS | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MATO GROSSO DO SUL |
| MG | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MINAS GERAIS |
| PA | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PARA |
| PB | SECRETARIA DA FAZENDA - GOV. DO ESTADO DA PARAIBA |
| PR | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PARANA |
| PE | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE PERNAMBUCO |
| PI | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PIAUI |
| RJ | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO DE JANEIRO |
| RN | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO GRANDE DO NORTE |
| RS | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO GRANDE DO SUL |
| RO | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE RONDONIA |
| RR | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE RORAIMA |
| SC | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SANTA CATARINA |
| SP | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SAO PAULO |
| SE | SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SERGIPE |
| TO | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO TOCANTINS |

## Campos Preenchidos no ERP

| Campo | Valor |
|-------|-------|
| **Fornecedor** | SECRETARIA DA FAZENDA - GOV. DO ESTADO DO [UF] (via lookup) |
| **Valor** | Extraído do PDF |
| **Vencimento** | Data original do PDF (sem ajuste) |
| **Filial** | Extraída do PDF (1º número após "Razão Social") |
| **Referência** | `REF-GNRE {Nº Documento}` |
| **Nr. Nota Fiscal** | `REF-GNRE {Nº Documento}` |
| **Observação** | `REF-GNRE {Nº Documento}` |

## Fluxo da Automação

1. Lê o PDF com pdfplumber
2. Detecta tipo "GNRE" pelo texto "Guia Nacional de Recolhimento"
3. Extrai UF, valor, vencimento, documento e filial
4. Mapeia UF para nome do fornecedor
5. Abre navegador (Playwright Chromium)
6. Login no ERP
7. Navega até grid de títulos
8. Define tipo favorecido como **FORNECEDOR**
9. **Abre lookup de fornecedor** (`#btnLookupJanela_ttp_fornecedor_id`)
10. Busca pelo **nome do estado** (ex: "PERNAMBUCO") no campo `#txtPesquisa`
11. Clica no link da secretaria correspondente
12. **Filtra o grid** (`#ConfirmaFiltroS`)
13. Busca título existente do fornecedor (qualquer status: Pendente/Pago)
14. Clica **"Copiar"** → confirma "Sim"
15. Preenche campos (valor, vencimento, referência, NF, observação, filial)
16. Clica **"Alterar"** → confirma "Sim"
17. Anexa PDF ao título (aba Documentos → GED)
18. Emite e faz o download da **Autorização de Pagamento oficial em PDF** (`#ImprAutPagto` / `f_ImprAutPagto()`)

## Pontos Críticos Aprendidos

- **LOOKUP é obrigatório** para GNRE. A seleção mais confiável é marcar o checkbox `.eng-lookup-multi-chk` da Secretaria correspondente e clicar em `#btConfirmarSelecao`.
- Buscar no lookup pelo **nome do estado** (ex: "BAHIA", "ALAGOAS") funciona melhor que pela sigla (ex: "BA", "AL")
- Após selecionar no lookup, **sempre clicar `#ConfirmaFiltroS`** para o grid mostrar os títulos
- Se não houver título **Pendente**, usar qualquer título (inclusive **Pago**) para copiar
- **Filial** vem do 1º número após "Razão Social" no PDF (ex: `551 COMERCIO...` → filial 551)
- **Nº Documento** extraído do final da linha "Telefone:"

## Extração do Nº Documento

O número do documento está no final da linha do Telefone no PDF. Dois formatos comuns:

| Formato no PDF | Extraído |
|----------------|----------|
| `Telefone:1155723945 29014` | `29014` |
| `Telefone: 000002861` | `2861` |

A regex `r"Telefone:.*?(\d+)$"` captura todos os dígitos no final da linha.

## Arquivos do Projeto

| Arquivo | Descrição |
|---------|-----------|
| `src/main.py` | Entry point, lê PDFs e orquestra o lançamento |
| `src/pdf_parser.py` | Parsers por tipo (GNRE, DAS, Boleto, Genérico) + OCR fallback |
| `src/erp_launcher.py` | Automação no ERP (Playwright/Camoufox) |
| `.env` | Configurações (URL, credenciais, filial, Camoufox) |
| `GNRE NF {num}.pdf` | PDF da GNRE a ser processado |

## Configuração (.env)

```
ERP_URL=https://erp.admsis.com/Home?eng_tela=0103070100
ERP_USERNAME=seu_usuario
ERP_PASSWORD=sua_senha
FILIAL_PADRAO=429
USE_CAMOUFOX=True
```

## Tecnologias

- Python 3.11+
- Playwright (Chromium) ou Camoufox (Firefox c/ anti-detection)
- pdfplumber
- pytesseract (fallback OCR)

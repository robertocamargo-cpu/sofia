# Lançamento de Boletos RELEVO no ERP — Fluxo Completo

## Visão Geral

Automação para ler PDFs de boletos da **RELEVO ARTEFATOS DE PAPEL LTDA** (FOR 00291), extrair os dados e lançar o título no ERP ADMSIS.

---

## Dados Extraídos do PDF

| Campo | Origem no PDF | Exemplo |
|-------|---------------|---------|
| **Fornecedor** | Linha após "Beneficiário" / "Nome:" | `RELEVO ARTEFATOS DE PAPEL LTDA` |
| **Valor** | Campo "Valor final" ou "Valor documento" | `R$ 6.848,69` |
| **Vencimento** | Campo "Vencimento" | `13/08/2026` |
| **Nº Documento** | Linha "Data de documento / N° documento" | `0020076900042037` |
| **Filial** | Fixa do `.env` | `429` |

## Senha dos PDFs

Os PDFs dos boletos são protegidos por senha. A senha são os **5 primeiros dígitos do CNPJ da filial 429**.

| Item | Valor |
|------|-------|
| CNPJ da Filial 429 | `05.393.606/0001-58` |
| Senha do PDF | `05393` |
| Config no `.env` | `PDF_PASSWORD=05393` |

## Campos Preenchidos no ERP

| Campo | Valor |
|-------|-------|
| **Fornecedor** | RELEVO ARTEFATOS DE PAPEL LTDA |
| **Valor** | Extraído do PDF (ex: `6848,69`) |
| **Vencimento** | Ajustado: dia anterior ao vencimento (dias úteis) |
| **Filial** | `429` (fixa) |
| **Referência** | `REF-Boleto {Nº Documento}` |
| **Nr. Nota Fiscal** | `REF-Boleto {Nº Documento}` |
| **Observação** | `REF-Boleto {Nº Documento}` |

## Fluxo da Automação

1. Lê o PDF com pdfplumber (senha `05393`)
2. Aplica **desduplicação de caracteres** (corrige texto com letras duplicadas tipo "BBeenneeffiicciiáárriioo")
3. Detecta tipo "Boleto" por palavras-chave ("Beneficiário", "Pagador", "Linha digitável")
4. Extrai fornecedor, valor, vencimento e nº documento
5. Abre navegador (Playwright ou Camoufox)
6. Login no ERP
7. Navega até grid de títulos
8. Seleciona tipo "FORNECEDOR"
9. Busca fornecedor "RELEVO ARTEFATOS DE PAPEL LTDA" no lookup
10. Filtra o grid (`#ConfirmaFiltroS`)
11. **Ordena por Data Vencimento ASC** (`#header_ttp_data_vencimento`)
12. **Seleciona o primeiro título** (mais recente após ordenação)
13. Clica "Copiar"
14. Preenche campos (valor, vencimento, referência, NF, observação, filial 429)
15. Clica "Alterar" e confirma para salvar o novo título
16. **Sem fechar o título recém-salvo**, clica diretamente na aba "Documentos"
17. Clica em "+ Novo" no iframe de documentos (EngGedList)
18. No iframe de upload (EngGedNovo), preenche a descrição como "boleto"
19. Faz o upload do arquivo PDF clicando em "CLIQUE AQUI PARA SELECIONAR O ARQUIVO"
20. Clica em "Carregar Arquivo" para anexar o documento
21. Valida que o anexo aparece no grid e fecha a janela do título
## Tratamento de PDFs com Caracteres Duplicados

Alguns boletos têm o texto extraído com caracteres duplicados (ex: "VVaalloorr" em vez de "Valor"). A função `deduplicate_chars()` em `pdf_parser.py` corrige isso:

```python
def deduplicate_chars(text: str) -> str:
    return re.sub(r"([A-Za-zÀ-ÿ])\1+", lambda m: m.group(1).upper(), text)
```

- Remove repetições de letras consecutivas (ex: `BB` → `B`, `ee` → `E`)
- Preserva números inalterados (evita corromper CNPJ, documento, etc.)

## Arquivos do Projeto

| Arquivo | Descrição |
|---------|-----------|
| `src/main.py` | Entry point, lê PDFs e orquestra o lançamento |
| `src/pdf_parser.py` | Parsers por tipo + OCR fallback + desduplicação |
| `src/erp_launcher.py` | Automação no ERP (Playwright/Camoufox) |
| `.env` | Configurações (URL, credenciais, filial, senha PDF) |
| `RELEVO.md` | Este documento |

## Configuração (.env)

```
ERP_URL=https://erp.admsis.com/Home?eng_tela=0103070100
ERP_USERNAME=seu_usuario
ERP_PASSWORD=sua_senha
FILIAL_PADRAO=429
USE_CAMOUFOX=True
PDF_PASSWORD=05393
```

## Tecnologias

- Python 3.11+
- Playwright (Chromium) ou Camoufox (Firefox c/ anti-detection)
- pdfplumber
- pytesseract (fallback OCR)

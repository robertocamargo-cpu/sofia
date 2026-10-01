# 🏆 Fluxo de Automação: Incentivo / Prêmio de Vendas (Nevine & SofIA)

Este documento descreve o fluxo de apuração e cálculo automatizado de **Incentivos e Bônus Comerciais de Vendas da Nevine** integrado nativamente à assistente **SofIA**.

---

## 🎯 1. Visão Geral do Processo

- **Objetivo:** Calcular automaticamente o bônus/incentivo de vendas de cada consultor(a) comercial a partir da planilha oficial do Google Sheets, aplicando as regras de validação de pedidos, exclusões de status e critérios de bonificação (F1 e F2).
- **Módulo Python:** `src/premio_launcher.py`
- **Fonte de Dados Oficial:** Google Sheets (Exportação direta em CSV via GID `827221464` ou variável de ambiente `PREMIO_SHEETS_URL`)
- **Formatos de Saída:**
  - Tabela resumo formatada no Discord (com ranking, totais e desdobramentos F1/F2).
  - Relatório analítico executivo em **HTML** (`logs/relatorio_premio_<periodo>.html`).
  - Relatório executivo oficial em **PDF A4** (`logs/relatorio_premio_<periodo>.pdf`) gerado via Playwright Chromium.
  - Registro de auditoria no histórico estruturado (`data/batch_history.json`).

---

## 📋 2. Regras de Negócio e Critérios de Bonificação

### 2.1. Exclusão Global de Status
Pedidos que estejam com os seguintes status no campo `siv_descricao` são **desconsiderados** da apuração:
- `APROVACAO`
- `ANALISE DE CREDITO`
- `VENDEDOR`
- `FATURAMENTO DENEGADO`
- `CANCELADO`

### 2.2. Critério de Bonificação Filtro 1 (F1 - Cliente Novo)
Aplica-se a pedidos que atendam simultaneamente aos dois critérios:
1. `ind_cliente_novo` igual a `"CLIENTE NOVO"`
2. `ope_descricao` igual a `"* VENDA"`

### 2.3. Critério de Bonificação Filtro 2 (F2 - Espaço Nevine)
Aplica-se a pedidos que atendam cumulativamente a:
1. `ind_cliente_novo` vazio/nulo (não é cliente novo)
2. `ope_descricao` contendo o termo `"ESPAÇO NEVINE"`

### 2.4. Cálculos Financeiros
- **Valor da Venda:** Campo `valor_total` do pedido.
- **Valor do Prêmio:** Campo `PREMIO` da linha da planilha.
- **Total por Vendedor:** Soma de `PREMIO` (F1 + F2) e soma de `valor_total` (F1 + F2).
- **Ranking:** Ordenado do maior prêmio total apurado para o menor.

---

## ⚡ 3. Performance e Cache Inteligente

A planilha oficial possui mais de **13.700 linhas** (~11 MB). Para garantir respostas imediatas no Discord:
- O módulo utiliza um **cache local de alta velocidade** em `logs/planilha_google_cache.csv` com TTL de **10 minutos**.
- Se múltiplos usuários solicitarem relatórios em sequência, a apuração é instantânea (< 1 segundo).
- O download automático com retry (até 3 tentativas) é executado caso o cache expire ou seja forçado.

---

## 💬 4. Como Chamar no Discord

A assistente SofIA reconhece naturalmente períodos informados no comando:

> **Mês Anterior (Padrão):**  
> `@SofIA apurar incentivo` ou `@SofIA calcule o prêmio`  
> *(Calcula automaticamente o mês anterior completo)*

> **Mês Específico por Nome:**  
> `@SofIA calcule o prêmio de setembro`  
> `@SofIA qual a comissão de agosto?`  
> `@SofIA incentivo de outubro`

> **Mês Atual até Hoje:**  
> `@SofIA prêmio deste mês`  
> `@SofIA incentivo do mês atual`

> **Período Customizado (Data a Data):**  
> `@SofIA apurar prêmio de 01/09/2026 até 15/09/2026`

---

## 🖥️ 5. Como Executar via Terminal / CLI

Você também pode executar a apuração diretamente via linha de comando no PowerShell ou CMD:

```powershell
# Apura o mês anterior (padrão)
python src/premio_launcher.py

# Apura um mês específico
python src/premio_launcher.py "setembro"

# Apura intervalo de datas
python src/premio_launcher.py "01/09/2026 a 15/09/2026"
```

---

## 📊 6. Exemplo de Resumo Gerado

```text
Pos  | Vendedor           | Pedidos | Prêmio Total
----------------------------------------------
1º   | AURORA DUTRA       | 38      | R$ 496,72
2º   | JULIANA SANCHES    | 16      | R$ 189,83
3º   | SITE               | 8       | R$ 100,47
----------------------------------------------
TOTAL: 62 pedidos elegíveis | R$ 787,02 de premiação total
```

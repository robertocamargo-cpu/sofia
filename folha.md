# 👥 Fluxo de Automação: Folha de Pagamento / Salários (ERP ADMSIS & SofIA)

Este documento descreve o fluxo de lançamento em lote da **Folha de Pagamento Mensal de Salários** no ERP ADMSIS a partir da planilha/relatório em PDF contendo o **Resumo de Líquido (Relação Geral dos Líquidos)**.

---

## 🎯 1. Visão Geral do Processo

- **Objetivo:** Automatizar o lançamento do pagamento líquido de salários de todos os colaboradores por filial (`429`, `601`, `Nevine`), clonando as parametrizações fiscais e contábeis de salários no ERP ADMSIS.
- **Tela no ERP:** `0103070100` (`Financeiro / Títulos a Pagar`)
- **Filtro de Favorecido:** `Funcionário` (Tipo `3`)
- **Plano de Contas:** `SALÁRIOS / FOLHA DE PAGAMENTO`
- **Requisito Obrigatório:** Envio do arquivo PDF contendo a **Relação Geral dos Líquidos** (Resumo de Líquido emitido pelo sistema de folha/RH).

---

## 📋 2. Requisitos e Regras de Negócio

1. **Envio Obrigatório do PDF:**
   - Para disparar o lançamento de Folha de Pagamento, o usuário deve **obrigatoriamente anexar o PDF com o resumo de valores líquidos** junto ao comando no Discord.
   - Caso o usuário envie apenas o comando de texto sem o anexo, a SofIA não executa e avisa imediatamente no chat com as instruções de preenchimento.

2. **Extração Automática dos Dados do PDF:**
   - **Competência:** Extraída do cabeçalho (ex: `Competência: 06/2026`).
   - **Data de Vencimento:** 5º dia útil do mês subsequente (ou data de vencimento expressa na folha).
   - **Colaboradores e Valores:** Extração linha a linha contendo Código, Nome do Colaborador, CPF e Valor Líquido a Receber.

3. **Filiais Suportadas:**
   - `601` (COMERCIO SERVICOS E CONFECCOES)
   - `429` (CONFECCOES)
   - `NEVINE` (NEVINE COMERCIO)

---

## 💬 3. Como Chamar no Discord

> **Comando:**  
> `@SofIA lance folha de pagamento filial 601` *(anexando o PDF do Resumo de Líquido)*  
> ou  
> `sofia lance pagamento filial nevine` *(anexando o PDF do Resumo de Líquido)*

---

## 🖥️ 4. Fluxo de Execução no ERP (Playwright)

1. Valida o recebimento do PDF anexado.
2. Faz o parsing do relatório extraindo cada colaborador e seu valor líquido.
3. Entra na tela `0103070100` e filtra por Funcionários com referência `Salario`.
4. Para cada colaborador:
   - Clona o título base correspondente (`#Copiar`).
   - Seleciona o funcionário no lookup.
   - Preenche o valor líquido, filial, referência (`Salário - MM/AAAA`) e vencimento.
   - Grava com `#AlterarI`.
5. Salva o resumo de execução em `data/batch_history.json`.
6. Responde no Discord com a tabela consolidada de colaboradores gravados com sucesso.

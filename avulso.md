# 💸 Fluxo de Automação: Pagamento Avulso (ERP ADMSIS & SofIA)

Este documento descreve detalhadamente o fluxo de lançamento e duplicação automatizada de **Pagamentos Avulsos** (pagamentos realizados via PIX, TED, dinheiro ou transferência bancária sem boleto físico ou título de cobrança prévio) no ERP ADMSIS e sua orquestração pela assistente **SofIA** no Discord.

---

## 🎯 1. Visão Geral do Processo

- **Objetivo:** Permitir o lançamento rápido e seguro de despesas avulsas no ERP ADMSIS sem necessidade de cadastrar um título do zero. A automação localiza o fornecedor informado, identifica o último título realizado para ele, clica em **Copiar Título** (herdando plano de contas, rateio contábil e parametrizações fiscais), atualiza os dados variáveis e grava o registro.
- **Tela no ERP:** `0103070100` (`Financeiro / Títulos a Pagar`)
- **URL da Tela:** `https://erp.admsis.com/Home?eng_tela=0103070100`
- **Módulos do Sistema:**
  - [`src/avulso_launcher.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/src/avulso_launcher.py) — Motor Playwright para busca, clonagem e gravação.
  - [`run_avulso.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/run_avulso.py) — Script para execução via linha de comando (CLI).
  - [`sofia_bot.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/sofia_bot.py) — Assistente conversacional no Discord com validação prévia de campos.

---

## 🖥️ 2. Mapeamento de Elementos e Ações no ERP ADMSIS

| Etapa | Ação no Sistema | Seletor HTML / Ação | Observações / Regra de Negócio |
| :--- | :--- | :--- | :--- |
| **1. Acesso à Tela** | Navegar para Títulos a Pagar | `page.goto("...eng_tela=0103070100")` | Aguarda carregamento completo do grid. |
| **2. Campo Fornecedor** | Input de pesquisa no cabeçalho | `<input id="pesq_ttp_fornecedor_id">` | Campo de pesquisa textual de fornecedor no topo da tela. |
| **3. Lookup de Fornecedor** | Abrir janela de pesquisa | `#btnLookupJanela_ttp_fornecedor_id` | Aciona o modal `EngAjaxLookup`. |
| **4. Buscar Fornecedor** | Digitar nome no lookup | `#txtPesquisa` & `#btEnviar` | Digita o termo (ex: `EDUARDO LAURINDO`) e filtra. |
| **5. Selecionar Favorecido**| Ticar a linha correspondente | `input.eng-lookup-multi-chk` ou `<td>` | Ex: `<td>EDUARDO LAURINDO DA SILVA</td>`. |
| **6. Confirmar Seleção** | Aplicar favorecido selecionado | `<button id="btConfirmarSelecao">` | Retorna o ID do fornecedor para a tela principal. |
| **7. Filtrar Grid** | Filtrar títulos do favorecido | `<button id="ConfirmaFiltroS">` (`<span class="fa fa-filter">`) | Recarrega o grid listando o histórico do fornecedor. |
| **8. Localizar Último Título**| Ordenar DESC e obter o mais recente | Ordena com `ttp_id DESC` e clica no primeiro `btnEd_1` | Garante SEMPRE a herança das parametrizações contábeis do último título feito. |
| **9. Copiar Título** | Acionar ação de cópia | `<button id="Copiar" onclick="f_Copiar()">` | Dispara a clonagem do título; aceita o diálogo `"Sim"`. |
| **10. Preencher Valor** | Informar o valor do pagamento | `<input id="ttp_valor_titulo">` | Formatação em moeda brasileira (ex: `760` $\rightarrow$ `760,00`). |
| **11. Preencher Filial** | Vincular à filial solicitada | `<select id="ttp_filial_id">` | Seleciona a filial de custo (ex: `429`, `601`, `Nevine`, etc.). |
| **12. Preencher Referência** | Definir a referência/NF | `<input id="ttp_referencia">` | **Obrigatório:** Texto informado no Discord. Se ausente, a SofIA pausa e solicita. |
| **13. Preencher Vencimento**| Definir a data do pagamento | `<input id="ttp_data_vencimento">` | **Obrigatório:** Digitação de 8 dígitos (`DDMMAAAA`) com `change` e `blur`. |
| **14. Observação / Histórico**| Histórico da despesa | `<textarea id="ttp_historico">` | Se informada no Discord, atualiza; se não informada, **mantém como está** da cópia. |
| **15. Gravação** | Salvar o novo título | `<button id="AlterarI">` (`Alterar`) | Grava o título clonado e confirma `"Sim"`. |

---

## 🤖 3. Regras de Negócio e Validação Conversacional (Discord)

Para garantir segurança contábil e evitar lançamentos inconsistentes no ERP:

### A. Matriz de Campos Obrigatórios vs. Opcionais

| Campo | Obrigatório? | Comportamento se NÃO for informado no Discord |
| :--- | :---: | :--- |
| **Favorecido / Fornecedor** | Sim | Retorna erro solicitando o nome do favorecido. |
| **Valor (R$)** | Sim | Retorna erro solicitando o valor. |
| **Filial** | Sim | Se não informado, utiliza a filial padrão configurada no `.env` (`FILIAL_PADRAO=429`). |
| **Referência** | **Sim** | **A SofIA interrompe a execução e pergunta no Discord:** *"Qual é a referência do pagamento?"* |
| **Data de Vencimento** | **Sim** | **A SofIA interrompe a execução e pergunta no Discord:** *"Qual é a data de vencimento?"* (Aceita `hoje`, `amanhã` ou `DD/MM/AAAA`). |
| **Observação** | Não | **Mantém o conteúdo original** herdado do título clonado. Se o usuário fornecer, substitui. |

### B. Validação Prévia Inteligente (*Fail-Fast*)
A assistente analisa a mensagem do usuário antes de iniciar o navegador Playwright:
* Se faltar **Referência** ou **Data de Vencimento**, a SofIA responde **imediatamente** no chat com um formulário amigável de preenchimento, **sem abrir o ERP** nem consumir tempo da fila de processamento.

---

## 💬 4. Exemplos de Comandos no Discord

### Exemplo 1: Comando Completo em Linha Única (Execução Direta)
> **Usuário:**  
> `@SofIA lance o pagamento avulso para EDUARDO LAURINDO, valor 760, filial 429, ref SERVIÇO MANUTENÇÃO ELÉTRICA, vencimento hoje`
>
> **SofIA:**  
> 1. Valida todos os campos obrigatórios.  
> 2. Adquire o lock de sessão do ERP.  
> 3. Entra no grid, pesquisa `EDUARDO LAURINDO`, seleciona o fornecedor e filtra.  
> 4. Abre o último título feito para ele e clica em `Copiar Título`.  
> 5. Atualiza Valor (`R$ 760,00`), Filial (`429`), Referência (`SERVIÇO MANUTENÇÃO ELÉTRICA`) e Vencimento (`30/09/2026`).  
> 6. Salva e responde no Discord com a tabela formatada do título gravado.

---

### Exemplo 2: Comando com Campos Faltantes (SofIA solicita dados)
> **Usuário:**  
> `@SofIA lance o pagamento avulso para EDUARDO LAURINDO, valor 760, filial 429`
>
> **SofIA:**  
> ⚠️ **Pagamento Avulso Detectado!**  
> Para prosseguir com o lançamento de **EDUARDO LAURINDO** no valor de **R$ 760,00 (Filial 429)**, por favor informe:  
> • 📋 **Referência:** (ex: `ref MANUTENCAO PREDIAL`)  
> • 📅 **Data de Vencimento:** (ex: `vencimento hoje`, `vencimento amanhã` ou `vencimento 05/10/2026`)  
> • 📝 *(Opcional)* **Observação:** (se desejar alterar a observação herdada)
>
> **Usuário:**  
> `ref MANUTENÇÃO PREDIAL, vencimento 05/10/2026`
>
> **SofIA:**  
> ✅ Dados completos recebidos! Iniciando lançamento no ERP ADMSIS...

---

## 💻 5. Execução via Linha de Comando (CLI)

Você também pode executar diretamente pelo terminal para testes rápidos:

```bash
# Execução completa com argumentos nomeados:
python run_avulso.py --fornecedor "EDUARDO LAURINDO" --valor 760 --filial 429 --ref "MANUTENCAO PREDIAL" --vencimento 30/09/2026

# Execução interativa (o terminal solicita os campos faltantes):
python run_avulso.py "EDUARDO LAURINDO" 760 429
```

---

## 💡 6. Dicas Técnicas e Sugestões de Melhoria

1. **Ordenação do Grid para o "Último Título":**
   - O ADMSIS por padrão lista registros por ordem de ID ou emissão. O robô deve garantir a seleção da linha mais recente (linha 1 do grid resultante pós-filtro) para clonar o plano de contas atualizado.
2. **Tratamento de Fornecedor Sem Histórico Prévio:**
   - Como a técnica é baseada em `Copiar Título`, se o fornecedor for recém-cadastrado e tiver **0 títulos** no grid, o botão Copiar não existirá.
   - *Melhoria:* O script detecta se o grid veio vazio e avisa no Discord: *"Nenhum título anterior encontrado para este fornecedor. É necessário efetuar o primeiro lançamento manualmente ou informar um fornecedor base de modelo."*
3. **Anexo Opcional de Comprovante PIX:**
   - Se o usuário anexar o comprovante do PIX ou recibo junto à mensagem de texto, a SofIA já salva o arquivo no GED (`Documentos`) do título recém-copiado antes de finalizar!
4. **Formatação de Moeda Flexível:**
   - O parser aceita tanto `760`, quanto `760.00`, `760,00` ou `R$ 760,00`.
5. **Datas Relativas Amigáveis:**
   - Suporte nativo para termos como `hoje`, `amanhã`, `ontem` ou formatos `DD/MM/AAAA`.

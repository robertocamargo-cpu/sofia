# Lançamento de VR (Vale Refeição) no ERP ADMSIS — Documentação Completa

## 1. Visão Geral

Este documento descreve as especificações técnicas, regras de negócio e procedimentos operacionais para o lançamento mensal dos títulos de **Vale Refeição (VR)** dos colaboradores das empresas do grupo no **ERP ADMSIS** (tela `0103070100` — *Financeiro / Títulos a Pagar*).

O processo é executado pelo bot **SofIA** (via comando no Discord `@SofIA faça o VR de outubro` ou via CLI `python run_vr.py`), que lê os valores exatos da planilha oficial `Planilha VR.xlsx`, pesquisa e clona os títulos de VR anteriores no ERP, preenche os dados específicos da competência e realiza a gravação no sistema.

---

## 2. Parâmetros Críticos do ERP ADMSIS (Tela 0103070100)

### 2.1 Tipo de Favorecido (`#ttp_favorecido_tp_id`)
> [!IMPORTANT]
> No ERP ADMSIS, o campo `<select name="ttp_favorecido_tp_id" id="ttp_favorecido_tp_id">` possui as seguintes opções:
> * `1` = **Fornecedor**
> * `2` = **Cliente**
> * `3` = **Funcionário**
> 
> **Regra Obrigatória**: O campo deve ser **sempre definido com valor `3` (Funcionário)**. Nunca utilizar valor `2` (Cliente), pois isso causa a seleção e repetição indevida de clientes nos títulos.

### 2.2 Botão Copiar Título (`#Copiar` / `f_Copiar`)
* **Elemento**: `<button id="Copiar" class="eng-no-print btn btn-primary" onclick="f_Copiar()"><span class="fa fa-copy"></span>&nbsp;Copiar Título</button>`
* **Ação do Sistema**: Aciona a ação de duplicação `103070105`, submetendo o formulário com `Action = FORM_OUTROS`.
* **Comportamento**: Cria um novo título herdando a filial, o plano de contas (`41038-VALE REFEICAO`), banco e parametrizações da despesa.

### 2.3 Botão e Fluxo de Lookup de Funcionário (`#btnLookupJanela_ttp_funcionario_id`)
* **Elemento**: `<button id="btnLookupJanela_ttp_funcionario_id" onclick="EngDialogs.popUp('ttp_funcionario_id', 'admtb_funcionario', 'fun_id', 'fun_nome:Funcionário', ...)">`
* **Campos Associados**:
  * `#ttp_funcionario_id`: ID numérico oculto do funcionário (ex: `116`, `178`).
  * `#pesq_ttp_funcionario_id`: Nome visível do funcionário.
  * `#ttp_favorecido`: Descrição completa do favorecido (ex: `FUN Ana Helena Albuquerque Roces`).
* **Modal de Busca (`EngAjaxLookup`)**:
  * Abre o iframe com `implementacao=admtb_funcionario`.
  * Preenche o campo `#txtPesquisa` com o nome do colaborador e clica em `#btEnviar`.
  * A seleção do funcionário correto é feita clicando no link do resultado `javascript:Selecionar('ID')`.

### 2.5 Campo Filial (`#ttp_filial_id`)
* **Elemento**: `<select name="ttp_filial_id" id="ttp_filial_id" class="form-control eng-campo eng-campo-requerido">`
* **Mapeamento Oficial de Valores**:
  * `value="155"` → **Filial 429**
  * `value="216"` → **Filial 601**
  * `value="293"` → **Filial Nevine**
  * `value="253"` → **Filial 302**
  * `value="161"` → **Filial 551**
  * `value="154"` → **Filial Relevo**

> [!CAUTION]
> **Atenção ao Comportamento do ERP**: Ao utilizar o botão **Copiar Título**, o novo título gerado **herda a filial do título de origem**. Além disso, a troca de funcionário via popup de lookup (`#btnLookupJanela_ttp_funcionario_id`) **NÃO** altera o campo `#ttp_filial_id` automaticamente!
> 
> **Mecanismo de Dupla Proteção Implementado**:
> 1. **Seleção Inteligente da Base**: Títulos de colaboradores da 429 sempre clonam a base da 429 (`btnEd_8`); colaboradores da 601 clonam a base da 601 (`btnEd_1`).
> 2. **Configuração Forçada no Formulário**: Imediatamente após a cópia e a seleção do funcionário, o robô seleciona programaticamente o `<select id="ttp_filial_id">` com o valor exato (`155`, `216` ou `293`) e dispara o evento `change`.
> 3. **Conferência Pré-Gravação**: Antes de clicar em `Alterar`, o robô valida se o valor de `#ttp_filial_id` confere 100% com a filial exigida na planilha.

---

## 3. Mapeamento de Campos do Título de VR

| Campo no ERP | Identificador / Seletor | Regra de Preenchimento | Exemplo |
| :--- | :--- | :--- | :--- |
| **Tipo Favorecido** | `#ttp_favorecido_tp_id` | **Sempre `3` (Funcionário)** | `3` |
| **Funcionário** | `#ttp_funcionario_id` / `#pesq_ttp_funcionario_id` | Colaborador da planilha (via cópia ou lookup) | `Danilo Cordeiro Oliveira` |
| **Valor do Título** | `#ttp_valor_titulo` | Valor exato da planilha para o colaborador | `682,50` ou `325,00` |
| **Vencimento** | `#ttp_data_vencimento` | Último dia útil do mês anterior (8 dígitos sem barra) | `30092026` (`30/09/2026`) |
| **Referência** | `#ttp_referencia` | Formato padrão `VR - [Mês]/[Ano]` | `VR - Outubro/2026` |
| **Nr. Nota Fiscal** | `#ttp_numero_nota_fiscal` | Formato padrão `VR - [Mês]/[Ano]` | `VR - Outubro/2026` |
| **Observação** | `#ttp_observacao` | Formato padrão `VR - [Mês]/[Ano]` | `VR - Outubro/2026` |
| **Plano de Contas** | `#ttp_plano_conta_id` | `41038-VALE REFEICAO` | Herdado na cópia |
| **Filial** | `#ttp_filial_id` | Mapeado explicitamente: `155` (429), `216` (601), `293` (Nevine) | `155` |


---

## 4. Fonte de Dados (`Planilha VR.xlsx`) e Mapeamento de Filiais

O arquivo [Planilha VR.xlsx](file:///c:/Users/finan/OneDrive/%C3%81rea%20de%20Trabalho/automacao%20contas%20a%20pagar/Planilha%20VR.xlsx) contém uma aba para cada mês solicitado (ex: `OUTUBRO 2026`).

### 4.1 Mapeamento de CNPJs / Filiais
* **CNPJ `05.393.606/0001-58`** → Filial **429**
* **CNPJ `52.803.025/0001-27`** → Filial **601**
* **CNPJ `71.883.656/0001-48`** → Filial **NEVINE**

---

## 5. Tabela de Colaboradores (Exemplo: Competência Outubro/2026)

Total de **26 colaboradores** | Valor Total da Folha: **R$ 17.387,50**

### 5.1 Filial 429 — CNPJ `05.393.606/0001-58` (17 Colaboradores | R$ 11.245,00)
| # | Colaborador | CPF | Valor (R$) | Observações da Planilha |
|---|---|---|---|---|
| 1 | ALESSANDRA AGUIAR SANTOS | 376.048.248-11 | **R$ 325,00** | Férias 28/09 a 17/10 (10 dias) |
| 2 | ALESSANDRO VIANA DE SOUZA | 186.247.868-60 | **R$ 682,50** | Integral |
| 3 | CATIANI SANTOS NOVAES DO NASCIMENTO | 254.533.938-58 | **R$ 682,50** | Integral |
| 4 | CLERIUS JOSEPH | G220069W | **R$ 682,50** | Integral |
| 5 | CLOVIS DOS SANTOS OLIVEIRA | 272.972.598-96 | **R$ 682,50** | Integral |
| 6 | ERIK RIAN DOS SANTOS | 066.925.145-33 | **R$ 682,50** | Integral |
| 7 | ESTHER SILVA DOS SANTOS | 484.486.948-56 | **R$ 682,50** | Integral |
| 8 | IDALIA SANTOS DE ATHAYDE OLIVEIRA | 327.599.438-79 | **R$ 682,50** | Integral |
| 9 | ISLAYNE RUFINO GOMES | 151.778.324-06 | **R$ 682,50** | Integral |
| 10 | ISMAEL PINHO BORGES | 374.063.268-23 | **R$ 682,50** | Integral |
| 11 | LUCIENE ALMEIDA SANTOS | 043.198.035-74 | **R$ 682,50** | Integral |
| 12 | MARIA DE FÁTIMA OLIVEIRA DE MEDEIROS | 123.047.258-48 | **R$ 682,50** | Integral |
| 13 | MARIA SÃO PEDRO BRAZ SOUZA | 890.533.115-72 | **R$ 682,50** | Integral |
| 14 | MICAEL MAGNO SOUTO ROSENDO | 466.862.428-45 | **R$ 682,50** | Integral |
| 15 | PRISCILA MARIA DO NASCIMENTO | 383.326.748-83 | **R$ 682,50** | Integral |
| 16 | SOLANGE PIMENTEL | 168.896.018-07 | **R$ 682,50** | Integral |
| 17 | VINICIUS MORENO MUSTAFA | 434.067.308-09 | **R$ 682,50** | Integral |

### 5.2 Filial 601 — CNPJ `52.803.025/0001-27` (7 Colaboradores | R$ 4.777,50)
| # | Colaborador | CPF | Valor (R$) | Observações da Planilha |
|---|---|---|---|---|
| 18 | ANA HELENA ALBUQUERQUE ROCES | 268.938.088-95 | **R$ 682,50** | Integral |
| 19 | ARNALDO CESAR ACERBI | 044.673.748-84 | **R$ 682,50** | Integral |
| 20 | AURORA LENIRDA DUTRA | 402.997.326-49 | **R$ 682,50** | Integral |
| 21 | FERNANDO FELIPE | 249.085.898-01 | **R$ 682,50** | Integral |
| 22 | HELENA EUFRASIO | 251.612.848-70 | **R$ 682,50** | Integral |
| 23 | JULIANA SANCHES OLIVEIRA DE PAULA | 372.901.728-41 | **R$ 682,50** | Integral |
| 24 | PAULO VINICIUS RODRIGUES FERNANDES | 426.201.318-98 | **R$ 682,50** | Integral |

### 5.3 Filial NEVINE — CNPJ `71.883.656/0001-48` (2 Colaboradoras | R$ 1.365,00)
| # | Colaborador | CPF | Valor (R$) | Observações da Planilha |
|---|---|---|---|---|
| 25 | GABRIELA DA SILVA LACANNA | 560.173.108-01 | **R$ 682,50** | Integral |
| 26 | DANIELA GIUNZIONI | 274.281.458-21 | **R$ 682,50** | Integral |

---

## 6. Fluxo de Execução Técnica da Automação

O algoritmo implementado em [src/vr_launcher.py](file:///c:/Users/finan/OneDrive/%C3%81rea%20de%20Trabalho/automacao%20contas%20a%20pagar/src/vr_launcher.py) opera de forma resiliente em 2 cenários:

```
                          ┌───────────────────────────┐
                          │ Ler Planilha do Mês Sol.  │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Filtrar Grid ERP:         │
                          │ Favorecido = FUNCIONÁRIO  │
                          │ Referência = VR Histórico │
                          └─────────────┬─────────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
┌─────────────────────────────┐                       ┌─────────────────────────────┐
│ CASO 1: Colaborador possui  │                       │ CASO 2: Colaborador novo /  │
│ título histórico no grid    │                       │ sem histórico no grid       │
└────────────┬────────────────┘                       └────────────┬────────────────┘
             │                                                     │
             ▼                                                     ▼
┌─────────────────────────────┐                       ┌─────────────────────────────┐
│ 1. Abrir título do próprio  │                       │ 1. Abrir título base da     │
│    colaborador              │                       │    mesma FILIAL (429/601/N) │
│ 2. Clicar em #Copiar        │                       │ 2. Clicar em #Copiar        │
│ 3. Novo título gerado já    │                       │ 3. Clicar no Lookup         │
│    mantém favorecido exato  │                       │    #btnLookupJanela...      │
│                             │                       │ 4. Buscar e selecionar o    │
│                             │                       │    colaborador pelo nome    │
└────────────┬────────────────┘                       └────────────┬────────────────┘
             │                                                     │
             └──────────────────────────┬──────────────────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Atualizar Campos:         │
                          │ • FILIAL (#ttp_filial_id) │
                          │   (155=429 / 216=601/293=N│
                          │ • Valor Título (Planilha) │
                          │ • Vencimento (Fim de Mês) │
                          │ • Referência / Obs / NF   │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Validar Filial no Form    │
                          │ Salvar: Clicar #AlterarI  │
                          │ Retornar ao Grid          │
                          └───────────────────────────┘
```

---

## 7. Comprovação de Testes Validados em Produção

Foram executados testes de validação direta no ERP com confirmação dos dados gravados no banco:

1. **Validação do Caso 1 (Colaborador com Histórico)**:
   * **Colaborador**: Ana Helena Albuquerque Roces
   * **Filial Confirmada**: **601** (`value="216"`)
   * **Valor**: R$ 682,50
   * **Vencimento**: 30/09/2026
   * **Referência**: `VR - Outubro/2026`
   * **ID Gerado no ERP**: `917058` (Confirmado e validado)

2. **Validação do Caso 2 (Novo Colaborador via Lookup + Blindagem de Filial 429)**:
   * **Colaborador**: Catiani Santos Novaes do Nascimento
   * **Filial da Planilha**: **429** (CNPJ `05.393.606/0001-58`)
   * **Título Base Clonado**: `btnEd_8` (Alessandra de Aguiar Santos - Filial 429)
   * **Lookup Acionado**: `#btnLookupJanela_ttp_funcionario_id` → ID `178`
   * **Filial Gravada e Conferida**: **429** (`value="155"`)
   * **Valor**: R$ 682,50
   * **Vencimento**: 30/09/2026
   * **Referência**: `VR - Outubro/2026`
   * **Status no ERP**: Gravado com sucesso e Filial 429 confirmada no formulário.


---

## 8. Formas de Execução

1. **Via Discord (SofIA Bot)**:
   * Comando: `@SofIA faça o VR de outubro`
   * O bot lê a aba do mês em `Planilha VR.xlsx`, executa o lançamento no ERP e retorna um Embed com o resumo da folha, status de sucesso, valor total e quantidade de colaboradores.

2. **Via Linha de Comando (CLI)**:
   ```bash
   python run_vr.py "outubro 2026"
   ```

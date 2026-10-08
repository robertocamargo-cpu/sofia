from __future__ import annotations
import pdfplumber
import re
from datetime import datetime, date, timedelta
from abc import ABC, abstractmethod

def extract_text_from_pdf(pdf_path: str, password: str | None = None) -> str:
    kwargs = {}
    if password:
        kwargs["password"] = password
    with pdfplumber.open(pdf_path, **kwargs) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def extract_text_ocr(pdf_path: str, password: str | None = None) -> str | None:
    try:
        import pytesseract
        from PIL import Image
        tesseract_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for p in tesseract_paths:
            if __import__("os").path.exists(p):
                pytesseract.pytesseract_cmd = p
                break
        kwargs = {}
        if password:
            kwargs["password"] = password
        with pdfplumber.open(pdf_path, **kwargs) as pdf:
            texts = []
            for page in pdf.pages:
                img = page.to_image(resolution=300)
                texts.append(pytesseract.image_to_string(img.original, lang="por"))
            return "\n".join(texts)
    except Exception as e:
        print(f"  OCR fallback indisponivel: {e}")
        return None

def clean_garbled(text: str) -> str:
    garbled_count = sum(1 for c in text if ord(c) == 0xFFFD)
    if garbled_count > len(text) * 0.15:
        return None
    return text

def deduplicate_chars(text: str) -> str:
    return re.sub(r"([A-Za-zÀ-ÿ])\1{2,}", lambda m: m.group(1).upper(), text)

class BaseParser(ABC):
    tipo: str

    @abstractmethod
    def extract(self, text: str) -> dict | list[dict]:
        ...

UF_FAVORECIDA_MAP = {
    "AC": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO ACRE",
    "AL": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE ALAGOAS",
    "AP": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO AMAPA",
    "AM": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO AMAZONAS",
    "BA": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DA BAHIA",
    "CE": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO CEARA",
    "DF": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO DISTRITO FEDERAL",
    "ES": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO ESPIRITO SANTO",
    "GO": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE GOIAS",
    "MA": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO MARANHAO",
    "MT": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MATO GROSSO",
    "MS": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MATO GROSSO DO SUL",
    "MG": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE MINAS GERAIS",
    "PA": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PARA",
    "PB": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DA PARAIBA",
    "PR": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PARANA",
    "PE": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE PERNAMBUCO",
    "PI": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO PIAUI",
    "RJ": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO DE JANEIRO",
    "RN": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO GRANDE DO NORTE",
    "RS": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO RIO GRANDE DO SUL",
    "RO": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE RONDONIA",
    "RR": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE RORAIMA",
    "SC": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SANTA CATARINA",
    "SP": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SAO PAULO",
    "SE": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DE SERGIPE",
    "TO": "SECRETARIA DA FAZENDA - GOV. DO ESTADO DO TOCANTINS",
}

class GNREParser(BaseParser):
    tipo = "GNRE"

    def extract(self, text: str) -> dict:
        result = {"fornecedor": None, "valor": None, "vencimento": None, "tipo": "GNRE"}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        uf_match = re.search(r"UF Favorecida.*?\n.*?\n\s*([A-Z]{2})\b", text, re.DOTALL)
        if uf_match:
            uf = uf_match.group(1)
            result["uf"] = uf
            result["fornecedor"] = UF_FAVORECIDA_MAP.get(uf, f"SECRETARIA DA FAZENDA - GOV. DO ESTADO DO {uf}")
        if not result["fornecedor"]:
            for i, line in enumerate(lines):
                if "CNPJ/CPF/Insc" in line and i + 1 < len(lines):
                    m = re.match(r"(.+?)\s+\d{2}\.\d{3}\.\d{3}/", lines[i + 1])
                    if m:
                        result["fornecedor"] = m.group(1).strip()
                    break
        result["valor"] = self._extract_valor(text)
        result["vencimento"] = self._extract_vencimento(text)
        doc = self._extract_documento(text)
        if doc:
            result["documento"] = doc
        filial = self._extract_filial(text)
        if filial:
            result["filial"] = filial
        return result

    def _extract_documento(self, text: str) -> str | None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines:
            m = re.search(r"Telefone:.*?(\d+)$", line)
            if m:
                return m.group(1).lstrip("0") or m.group(1)
        for i, line in enumerate(lines):
            if "Documento de Origem" in line and i + 1 < len(lines):
                m = re.search(r"(\d{4,})$", lines[i + 1])
                if m:
                    return m.group(1).lstrip("0") or m.group(1)
        return None

    def _extract_filial(self, text: str) -> str | None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "Raz" in line and "Social" in line:
                if i + 1 < len(lines):
                    m = re.match(r"(\d+)", lines[i + 1])
                    if m:
                        return m.group(1)
        return None

    def _extract_valor(self, text: str) -> float | None:
        m = re.search(r"R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})", text)
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        return None

    def _extract_vencimento(self, text: str) -> datetime | None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if re.search(r"Data\s+de\s+Vencimento|Vencimento", line, re.IGNORECASE):
                # 1. Tenta encontrar data na mesma linha
                m = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                if m:
                    try:
                        return datetime.strptime(m.group(1), "%d/%m/%Y").date()
                    except ValueError:
                        pass
                # 2. Tenta encontrar data na linha seguinte (layout padrão de colunas da GNRE)
                if i + 1 < len(lines):
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", lines[i + 1])
                    if m:
                        try:
                            return datetime.strptime(m.group(1), "%d/%m/%Y").date()
                        except ValueError:
                            pass

        # 3. Fallback: Qualquer expressão Vencimento seguida de data
        m = re.search(r"Vencimento[^\d]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        return None

class DASParser(BaseParser):
    tipo = "DAS"

    def extract(self, text: str) -> dict:
        result = {"fornecedor": "RECEITA FEDERAL", "valor": None, "vencimento": None, "tipo": "DAS"}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "CNPJ" in line and i + 1 < len(lines):
                m = re.match(r"(.+?)\s+\d{2}\.\d{3}\.\d{3}/", lines[i + 1])
                if m:
                    result["fornecedor"] = m.group(1).strip()
                break
        result["valor"] = self._extract_valor(text)
        result["vencimento"] = self._extract_vencimento(text)
        return result

    def _extract_valor(self, text: str) -> float | None:
        m = re.search(r"R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})", text)
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        return None

    def _extract_vencimento(self, text: str) -> datetime | None:
        m = re.search(r"Vencimento[:\s]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        return None

class BoletoParser(BaseParser):
    tipo = "Boleto"

    def extract(self, text: str) -> dict:
        result = {"fornecedor": None, "valor": None, "vencimento": None, "tipo": "Boleto"}
        result["fornecedor"] = self._extract_fornecedor(text)
        result["valor"] = self._extract_valor(text)
        result["vencimento"] = self._extract_vencimento(text)
        doc = self._extract_documento(text)
        if doc:
            result["documento"] = doc
        ref = self._extract_referencia(text)
        if ref:
            result["nf_numero"] = ref.get("nf")
            result["parcela_atual"] = ref.get("parcela")
            result["total_parcelas"] = ref.get("total")
        return result

    def _extract_referencia(self, text: str) -> dict | None:
        m = re.search(r"Referente\s+ao\s+documento\s+(\d+)\s+(\d+)/(\d+)", text, re.IGNORECASE)
        if m:
            return {"nf": m.group(1), "parcela": int(m.group(2)), "total": int(m.group(3))}
        return None

    def _extract_documento(self, text: str) -> str | None:
        lines = [l.strip() for l in text.splitlines()]
        keywords = ["Núm. do documento", "Data do documento", "N. do doc", "Nº do documento", "N° documento"]
        for i, line in enumerate(lines):
            if any(k in line for k in keywords):
                if i + 1 < len(lines):
                    m = re.search(r"\d{2}/\d{2}/\d{4}\s+([\d\.]+)", lines[i + 1])
                    if m:
                        return m.group(1)
                    m2 = re.search(r"(\d{10,})", lines[i + 1])
                    if m2:
                        return m2.group(1)
        return None

    def _extract_fornecedor(self, text: str) -> str | None:
        lines = [l.strip() for l in text.splitlines()]
        # Match "Benefici[áa�]rio" handling PDF encoding issues
        for i, line in enumerate(lines):
            if "Benefici" in line and ("Ag" in line or "Código" in line or "CNPJ" in line or "CPF" in line):
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    m = re.match(r"([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)(?:\s+CNPJ|\s+CPF|\s+\d)", next_line)
                    if m:
                        return m.group(1).strip()
        # Fallback: direct regex with flexible character
        ben_match = re.search(
            r"Benefici[^\n]*rio[^\n]*\n\s*(?:Nome:\s*)?([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)(?:\s*\(|\s*-\s*\d|\s+CNPJ|\s+CPF|\s+Nome:)",
            text, re.IGNORECASE
        )
        if ben_match:
            return ben_match.group(1).strip()
        pag_match = re.search(
            r"Pagador[^\n]*\n\s*([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)(?:\s*-\s*CNPJ|\s+CPF/CNPJ)",
            text, re.IGNORECASE
        )
        if pag_match:
            return pag_match.group(1).strip()
        for line in lines:
            if len(line) > 5 and not re.match(r"^[_\-=.\s]+$", line):
                return line
        return None

    def _extract_valor(self, text: str) -> float | None:
        m = re.search(r"R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})", text)
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        return None

    def _extract_vencimento(self, text: str) -> datetime | None:
        m = re.search(r"Vencimento[:\s]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        return None

class GenericParser(BaseParser):
    tipo = "Desconhecido"

    def extract(self, text: str) -> dict:
        result = {"fornecedor": None, "valor": None, "vencimento": None, "tipo": "Desconhecido"}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines:
            if line and not re.match(r"^[_\-=.\s]+$", line) and len(line) > 5:
                result["fornecedor"] = line
                break
        result["valor"] = self._extract_valor(text)
        result["vencimento"] = self._extract_vencimento(text)
        return result

    def _extract_valor(self, text: str) -> float | None:
        m = re.search(r"R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})", text)
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        return None

    def _extract_vencimento(self, text: str) -> datetime | None:
        m = re.search(r"Vencimento[:\s]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        return None

class HoleritParser(BaseParser):
    tipo = "Holerit"

    def extract(self, text: str) -> list[dict]:
        results = []
        seen_names = set()
        # Use flexible regex to handle garbled chars: C�digo / Código
        blocks = re.split(r"C.digo\s+Nome\s+do\s+Funcion.rio", text)
        
        # O mês geral pode estar antes dos blocos (no cabeçalho)
        mes_match_global = re.search(r"(Janeiro|Fevereiro|Mar.o|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s+de\s+(\d{4})", text, re.IGNORECASE)
        vencimento_global = None
        if mes_match_global:
            mes_str = mes_match_global.group(1).lower()
            ano = int(mes_match_global.group(2))
            # Normalize garbled março
            mes_str = re.sub(r"mar.o", "março", mes_str)
            mes_map = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
            mes_num = mes_map.get(mes_str)
            if mes_num:
                vencimento_global = datetime(ano, mes_num, 20).date()
        
        if len(blocks) > 1:
            for block in blocks[1:]:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                if not lines:
                    continue
                
                # Ex: "5 GABRIELA DA SILVA LACANNA 354125 1 1"
                # After dedup: "5 GABRIELA DA SILVA LACANA 354125 1 1"
                # The split may leave header remnants (e.g. "CBO Departamento Filial")
                # as lines[0], so scan the first few lines for the name pattern.
                fornecedor = None
                for scan_line in lines[:5]:
                    name_match = re.match(r"^\d+\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)\s+\d{4,}", scan_line)
                    if name_match:
                        fornecedor = name_match.group(1).strip()
                        break
                if not fornecedor:
                    continue
                
                # Deduplicate: each employee appears twice in the PDF (company copy + employee copy)
                if fornecedor in seen_names:
                    continue
                seen_names.add(fornecedor)
                
                valor = None
                for i, line in enumerate(lines):
                    # Ex: "Valor Líquido 848,00" or "Valor L�quido 848,00"
                    m = re.search(r"Valor\s+L.quido\s+([\d\.,]+)", line, re.IGNORECASE)
                    if m:
                        try:
                            valor = float(m.group(1).replace(".", "").replace(",", "."))
                        except ValueError:
                            pass
                        break
                    
                    # Ex: "Valor Líquido" na linha i, "848,00" na linha i+1
                    if re.search(r"Valor\s+L.quido", line, re.IGNORECASE) and i + 1 < len(lines):
                        m2 = re.search(r"([\d\.,]+)", lines[i+1])
                        if m2:
                            try:
                                valor = float(m2.group(1).replace(".", "").replace(",", "."))
                            except ValueError:
                                pass
                            break
                            
                vencimento = vencimento_global
                if not vencimento:
                    vencimento = datetime.today().date()
                    
                results.append({
                    "fornecedor": fornecedor,
                    "valor": valor,
                    "vencimento": vencimento,
                    "tipo": "Holerit"
                })
        
        return results if results else [{"fornecedor": None, "valor": None, "vencimento": None, "tipo": "Holerit"}]

CNPJ_FILIAL_MAP = {
    "52.803.025/0001-27": "601",
    "71.883.656/0001-48": "NEVINE",
    "05.393.606/0001-58": "429",
}

class AdiantamentoParser(BaseParser):
    tipo = "Adiantamento"

    def extract(self, text: str) -> list[dict]:
        results = []
        
        # 1. Identifica CNPJ e Filial
        filial = "429"
        cnpj_match = re.search(r"CNPJ:\s*([\d\.\/\-]+)", text)
        if cnpj_match:
            cnpj_limpo = cnpj_match.group(1).strip()
            for cnpj_cad, fil_cad in CNPJ_FILIAL_MAP.items():
                if cnpj_cad in cnpj_limpo:
                    filial = fil_cad
                    break
        
        # 2. Identifica Competência e Vencimento (padrão dia 20 com ajuste para dia útil)
        comp_str = None
        vencimento = None
        comp_match = re.search(r"Compet.ncia:\s*(\d{2})/(\d{4})", text, re.IGNORECASE)
        if comp_match:
            mes_num = int(comp_match.group(1))
            ano_num = int(comp_match.group(2))
            comp_str = f"{mes_num:02d}/{ano_num}"
            vencimento = date(ano_num, mes_num, 20)
            while vencimento.weekday() >= 5:
                vencimento -= timedelta(days=1)
        else:
            mes_match_global = re.search(r"(Janeiro|Fevereiro|Mar.o|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s+de\s+(\d{4})", text, re.IGNORECASE)
            if mes_match_global:
                mes_str = mes_match_global.group(1).lower()
                ano_num = int(mes_match_global.group(2))
                mes_str = re.sub(r"mar.o", "março", mes_str)
                mes_map = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
                mes_num = mes_map.get(mes_str, 7)
                comp_str = f"{mes_num:02d}/{ano_num}"
                vencimento = date(ano_num, mes_num, 20)
                while vencimento.weekday() >= 5:
                    vencimento -= timedelta(days=1)
                    
        if not vencimento:
            vencimento = datetime.today().date()
            comp_str = f"{vencimento.month:02d}/{vencimento.year}"

        # 3. Caso A: Relação Geral dos Líquidos (ex: adiantamento_601.pdf / adiantamento_nevine.pdf)
        matches_relacao = re.findall(r"^\s*(\d+)\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+([\d\.,]+)", text, re.MULTILINE)
        if matches_relacao:
            for m in matches_relacao:
                cod, nome, cpf, val_str = m
                try:
                    valor = float(val_str.replace(".", "").replace(",", "."))
                except ValueError:
                    continue
                results.append({
                    "fornecedor": nome.strip(),
                    "codigo": cod.strip(),
                    "cpf": cpf.strip(),
                    "valor": valor,
                    "vencimento": vencimento,
                    "filial": filial,
                    "competencia": comp_str,
                    "referencia": f"Adiantamento de Salário - {comp_str}",
                    "tipo": "Adiantamento"
                })
            return results

        # 4. Caso B: Recibos Individuais de Adiantamento (Holerite tradicional)
        holerit_parser = HoleritParser()
        res_holerit = holerit_parser.extract(text)
        for r in res_holerit:
            if r.get("fornecedor"):
                r["filial"] = filial
                r["vencimento"] = vencimento
                r["competencia"] = comp_str
                r["referencia"] = f"Adiantamento de Salário - {comp_str}"
                r["tipo"] = "Adiantamento"
                results.append(r)

        return results if results else [{"fornecedor": None, "valor": None, "vencimento": None, "tipo": "Adiantamento"}]

class PagamentoParser(BaseParser):
    tipo = "Pagamento"

    def extract(self, text: str) -> list[dict]:
        results = []
        
        # 1. Identifica CNPJ e Filial
        filial = "429"
        cnpj_match = re.search(r"CNPJ:\s*([\d\.\/\-]+)", text)
        if cnpj_match:
            cnpj_limpo = cnpj_match.group(1).strip()
            for cnpj_cad, fil_cad in CNPJ_FILIAL_MAP.items():
                if cnpj_cad in cnpj_limpo:
                    filial = fil_cad
                    break
        
        # 2. Identifica Competência e Vencimento
        comp_str = None
        vencimento = None
        comp_match = re.search(r"Compet.ncia:\s*(\d{2})/(\d{4})", text, re.IGNORECASE)
        if comp_match:
            mes_num = int(comp_match.group(1))
            ano_num = int(comp_match.group(2))
            comp_str = f"{mes_num:02d}/{ano_num}"
            
        emissao_match = re.search(r"Emiss.o:\s*(\d{2})/(\d{2})/(\d{4})", text, re.IGNORECASE)
        if emissao_match:
            d = int(emissao_match.group(1))
            m = int(emissao_match.group(2))
            a = int(emissao_match.group(3))
            vencimento = date(a, m, d)
        elif comp_str:
            mes_prox = mes_num + 1 if mes_num < 12 else 1
            ano_prox = ano_num if mes_num < 12 else ano_num + 1
            vencimento = date(ano_prox, mes_prox, 5)
            while vencimento.weekday() >= 5:
                vencimento += timedelta(days=1)
                
        if not vencimento:
            vencimento = datetime.today().date()
            if not comp_str:
                comp_str = f"{vencimento.month:02d}/{vencimento.year}"

        # 3. Extrai colaboradores (Empregados e Contribuintes)
        matches_relacao = re.findall(r"^\s*(\d+)\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+([\d\.,]+)", text, re.MULTILINE)
        if matches_relacao:
            for m in matches_relacao:
                cod, nome, cpf, val_str = m
                try:
                    valor = float(val_str.replace(".", "").replace(",", "."))
                except ValueError:
                    continue
                results.append({
                    "fornecedor": nome.strip(),
                    "codigo": cod.strip(),
                    "cpf": cpf.strip(),
                    "valor": valor,
                    "vencimento": vencimento,
                    "filial": filial,
                    "competencia": comp_str,
                    "referencia": f"Salário - {comp_str}",
                    "tipo": "Pagamento"
                })
            return results

        # 4. Caso B: Recibo Individual (Holerite tradicional)
        holerit_parser = HoleritParser()
        res_holerit = holerit_parser.extract(text)
        for r in res_holerit:
            if r.get("fornecedor"):
                r["filial"] = filial
                r["vencimento"] = vencimento
                r["competencia"] = comp_str
                r["referencia"] = f"Salário - {comp_str}"
                r["tipo"] = "Pagamento"
                results.append(r)

        return results if results else [{"fornecedor": None, "valor": None, "vencimento": None, "tipo": "Pagamento"}]

PARSERS_BY_TYPE: list[type[BaseParser]] = [
    DASParser,
    GNREParser,
    BoletoParser,
    AdiantamentoParser,
    PagamentoParser,
    HoleritParser,
    GenericParser,
]

def detect_type(text: str) -> str:
    if re.search(r"C.lculo:\s*Folha\s+Mensal|Folha\s+Mensal", text, re.IGNORECASE):
        return "Pagamento"
    if re.search(r"RELA..O GERAL DOS L.QUIDOS", text, re.IGNORECASE):
        if re.search(r"Folha|Sal.rio", text, re.IGNORECASE):
            return "Pagamento"
        return "Adiantamento"
    if re.search(r"C.lculo:\s*Adiantamento", text, re.IGNORECASE):
        return "Adiantamento"
    if re.search(r"(Adiantamento\s+Mensalista|Adiantamento\s+de\s+Sal.rio)", text, re.IGNORECASE):
        return "Adiantamento"
    if re.search(r"SIMPLES NACIONAL|DAS\s*[–-]|DAS\b.*RECEITA", text, re.IGNORECASE):
        return "DAS"
    if re.search(r"\bGNRE\b|Guia Nacional de Recolhimento", text, re.IGNORECASE):
        return "GNRE"
    if re.search(r"Recibo\s+de\s+Pagamento|Nome\s+do\s+Funcion.rio", text, re.IGNORECASE):
        return "Holerit"
    if re.search(r"\bBoleto\b", text, re.IGNORECASE):
        return "Boleto"
    if re.search(r"Benefici[^\n]*rio.*Pagador|Linha digit[áa]vel|Nosso n[úu]mero", text, re.IGNORECASE):
        return "Boleto"
    if re.search(r"\bFatura\b", text, re.IGNORECASE):
        return "Fatura"
    return "Desconhecido"

def get_parser(tipo: str) -> BaseParser:
    for parser_cls in PARSERS_BY_TYPE:
        if parser_cls.tipo == tipo:
            return parser_cls()
    return GenericParser()

def extract_invoice_data(pdf_path: str, password: str | None = None) -> dict | list[dict]:
    text = extract_text_from_pdf(pdf_path, password=password)

    text = clean_garbled(text)
    if text:
        text = deduplicate_chars(text)

    if not text or len(text.strip()) < 20:
        print(f"  Texto via pdfplumber muito curto, tentando OCR...")
        text = extract_text_ocr(pdf_path, password=password)

    if not text:
        return {"fornecedor": None, "valor": None, "vencimento": None, "tipo": None}

    tipo = detect_type(text)
    parser = get_parser(tipo)
    return parser.extract(text)

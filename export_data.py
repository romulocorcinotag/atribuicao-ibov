"""
export_data.py — Exporta dados dos XMLs locais para parquets no diretorio data/
Esses parquets sao commitados no repo e usados pelo app na nuvem (Streamlit Cloud).

Uso:
    python export_data.py          # exporta tudo
    python export_data.py --since 2025-01-01  # exporta a partir de uma data
"""
import os
import sys
import glob
import shutil
import argparse
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# === Paths ===
XML_BASE = r"G:\Drives compartilhados\SisIntegra\AMBIENTE_PRODUCAO\Posicao_XML\Mellon"
CARTEIRA_RV_DATA = r"G:\Drives compartilhados\Gestao_AI\carteira_rv\data"
CARTEIRA_RV_CACHE = r"G:\Drives compartilhados\Gestao_AI\carteira_rv\cache"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# === Fund config (same as app.py) ===
FUNDOS_CONFIG = {
    "Synta FIA II": {"cnpj": "51564188000131", "xml_prefix": "FD51564188000131"},
    "Synta FIA": {"cnpj": "20214858000166", "xml_prefix": "FD20214858000166"},
}

SUBFUNDO_NAMES = {
    # --- Synta FIA II sub-fundos (10) ---
    "15578434000140": "Atmos Institucional",
    "28408121000196": "GTI Haifa FIA",
    "11961199000130": "Neo Navitas FIC FIA",
    "42831345000137": "NV FC FIA",
    "17157131000180": "Oceana Selection FIC",
    "26956042000194": "Oceana Valor 30 FIC",
    "49984812000108": "Organon Institucional",
    "13455174000190": "Santander Dividendos",
    "17898543000170": "BNY ARX Liquidez RF",
    "16565084000140": "SPX Apache FIA",
    # --- Synta FIA sub-fundos (6) ---
    "53827819000193": "Absolute Pace FIC FIM",
    "51427627000164": "Atmos Institucional S",
    "52070019000108": "Real Investor Inst FIA",
    "40226121000170": "Perfin Infra Equity FIA",
    "41632880000104": "SPX Falcon Inst MM",
    "39346123000114": "Tarpon GT Institucional",
    # --- Synta funds themselves ---
    "51564188000131": "Synta FIA II",
    "20214858000166": "Synta FIA",
}

# Master CNPJ mapping (feeder -> master, same as app.py)
MASTER_CNPJ_MAP = {
    "15578434000140": "17162816000114",   # Atmos Institucional -> Atmos Master
    "28408121000196": "09143435000160",   # GTI Haifa FIA -> GTI Dimona Master
    "11961199000130": "20889133000178",   # Neo Navitas FIC -> Neo Navitas Master
    "42831345000137": "32812291000109",   # NV FC FIA -> Navi Institucional Master FIF
    "17157131000180": "27227810000131",   # Oceana Selection -> Oceana Selection Master
    "26956042000194": "18454944000102",   # Oceana Valor 30 -> Oceana Valor Master
    "49984812000108": "38251507000190",   # Organon Institucional -> Organon Master FIA
    "13455174000190": "13455136000138",   # Santander Dividendos CIC -> Santander Div FI
    "17898543000170": None,               # BNY ARX Liquidez RF -> RF, nao explode
    "16565084000140": "16565084000140",   # SPX Apache FIA -> ele mesmo
    "53827819000193": "51752977000104",   # Absolute Pace FIC FIM -> Absolute Pace Master FIF MM
    "51427627000164": "17162816000114",   # Atmos Institucional S -> Atmos Master (mesmo)
    "52070019000108": "52070476000100",   # Real Investor FIC -> Real Investor Master
    "40226121000170": "39344972000139",   # Perfin Infra Equity FIC -> Perfin Infra Master
    "41632880000104": "15831948000166",   # SPX Falcon Inst -> SPX Falcon Master
    "39346123000114": "27389566000103",   # Tarpon GT Institucional -> Tarpon GT Master
}


def parse_synta_xml(filepath: str) -> dict:
    """Parse a Synta XML file (same logic as app.py)."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    fundo = root.find("fundo")
    if fundo is None:
        return {}
    header = fundo.find("header")
    result = {
        "cnpj": header.findtext("cnpj", ""),
        "nome": header.findtext("nome", ""),
        "dtposicao": header.findtext("dtposicao", ""),
        "patliq": float(header.findtext("patliq", "0") or 0),
        "valorcota": float(header.findtext("valorcota", "0") or 0),
        "quantidade_cotas": float(header.findtext("quantidade", "0") or 0),
        "posicoes": [],
    }
    pl = result["patliq"]
    if pl <= 0:
        return result

    # RF
    rf_valor = 0.0
    rf_qtd = 0.0
    for tp in fundo.findall("titpublico"):
        vf = float(tp.findtext("valorfindisp", "0") or 0)
        qtd = float(tp.findtext("qtdisponivel", "0") or 0)
        rf_valor += vf
        rf_qtd += qtd
    if rf_valor > 0:
        rf_pu = rf_valor / rf_qtd if rf_qtd > 0 else 0
        result["posicoes"].append({"componente": "Renda Fixa (LFT)", "tipo": "RF", "valor": rf_valor,
                                    "peso_pct": rf_valor / pl * 100, "pu": rf_pu, "qtd": rf_qtd, "vlajuste": 0})

    # Acoes
    acoes_map = {}
    for ac in fundo.findall("acoes"):
        cod = ac.findtext("codativo", "")
        classe = ac.findtext("classeoperacao", "C")
        vf_disp = float(ac.findtext("valorfindisp", "0") or 0)
        qtd_gar = float(ac.findtext("qtgarantia", "0") or 0)
        pu = float(ac.findtext("puposicao", "0") or 0)
        qtd_disp = float(ac.findtext("qtdisponivel", "0") or 0)
        if cod not in acoes_map:
            acoes_map[cod] = {"valor": 0.0, "qtd": 0.0, "pu": pu}
        if classe == "C":
            acoes_map[cod]["valor"] += vf_disp
            acoes_map[cod]["qtd"] += qtd_disp
        else:
            acoes_map[cod]["valor"] += qtd_gar * pu
            acoes_map[cod]["qtd"] += qtd_gar
    for cod, info in acoes_map.items():
        if info["valor"] > 0:
            result["posicoes"].append({"componente": cod, "tipo": "Acao/ETF", "valor": info["valor"],
                                        "peso_pct": info["valor"] / pl * 100, "pu": info["pu"], "qtd": info["qtd"], "vlajuste": 0})

    # Futuros
    for fut in fundo.findall("futuros"):
        ativo = fut.findtext("ativo", "")
        serie = fut.findtext("serie", "")
        vl = float(fut.findtext("vltotalpos", "0") or 0)
        vlaj = float(fut.findtext("vlajuste", "0") or 0)
        result["posicoes"].append({"componente": f"FUT {ativo} {serie}", "tipo": "Futuro", "valor": vl,
                                    "peso_pct": vl / pl * 100, "pu": 0, "qtd": 0, "vlajuste": vlaj})

    # Opcoes
    for op in fundo.findall("opcoes"):
        cod = op.findtext("codativo", "")
        vf = float(op.findtext("valorfinanceiro", "0") or 0)
        pu = float(op.findtext("puposicao", "0") or 0)
        qtd = float(op.findtext("qtdisponivel", "0") or 0)
        if vf != 0:
            result["posicoes"].append({"componente": f"OPC {cod}", "tipo": "Opcao", "valor": vf,
                                        "peso_pct": vf / pl * 100, "pu": pu, "qtd": qtd, "vlajuste": 0})
    for od in fundo.findall("opcoesderiv"):
        serie = od.findtext("serie", "")
        vf = float(od.findtext("valorfinanceiro", "0") or 0)
        pu = float(od.findtext("puposicao", "0") or 0)
        qtd = float(od.findtext("qtd", "0") or 0)
        if vf != 0:
            result["posicoes"].append({"componente": f"OPFUT {serie}", "tipo": "Opcao Futuro", "valor": vf,
                                        "peso_pct": vf / pl * 100, "pu": pu, "qtd": qtd, "vlajuste": 0})

    # Caixa
    for cx in fundo.findall("caixa"):
        saldo = float(cx.findtext("saldo", "0") or 0)
        if saldo != 0:
            result["posicoes"].append({"componente": "Caixa", "tipo": "Caixa", "valor": saldo,
                                        "peso_pct": saldo / pl * 100, "pu": 0, "qtd": 0, "vlajuste": 0})

    # Cotas de fundos
    for cota in fundo.findall("cotas"):
        cnpj_f = cota.findtext("cnpjfundo", "")
        qtd = float(cota.findtext("qtdisponivel", "0") or 0)
        pu = float(cota.findtext("puposicao", "0") or 0)
        valor = qtd * pu
        nome = SUBFUNDO_NAMES.get(cnpj_f, f"Fundo {cnpj_f}")
        result["posicoes"].append({"componente": nome, "tipo": "Fundo", "cnpj": cnpj_f, "valor": valor,
                                    "peso_pct": valor / pl * 100, "qtd_cotas": qtd, "pu": pu, "qtd": qtd, "vlajuste": 0})
    return result


def export_synta_timeseries(since_date=None):
    """Export all XML data to parquet files per fund."""
    os.makedirs(DATA_DIR, exist_ok=True)

    for fundo_key, config in FUNDOS_CONFIG.items():
        prefix = config["xml_prefix"]
        safe_name = fundo_key.lower().replace(" ", "_")
        out_path = os.path.join(DATA_DIR, f"timeseries_{safe_name}.parquet")

        print(f"\n=== Exportando {fundo_key} ===")
        all_rows = []
        folder_count = 0

        for folder_name in sorted(os.listdir(XML_BASE)):
            try:
                folder_date = datetime.strptime(folder_name, "%Y%m%d").date()
            except ValueError:
                continue

            if since_date and folder_date < since_date:
                continue

            folder = os.path.join(XML_BASE, folder_name)
            files = glob.glob(os.path.join(folder, f"{prefix}_*"))
            if not files:
                continue

            parsed = parse_synta_xml(files[0])
            if not parsed or not parsed.get("posicoes"):
                continue

            folder_count += 1
            for pos in parsed["posicoes"]:
                row = {
                    "data": pd.Timestamp(folder_date),
                    "componente": pos["componente"],
                    "tipo": pos["tipo"],
                    "valor": pos["valor"],
                    "peso_pct": pos["peso_pct"],
                    "patliq": parsed["patliq"],
                    "valorcota": parsed["valorcota"],
                    "pu": pos.get("pu", 0),
                    "vlajuste": pos.get("vlajuste", 0),
                }
                if pos.get("cnpj"):
                    row["cnpj"] = pos["cnpj"]
                all_rows.append(row)

        if all_rows:
            df = pd.DataFrame(all_rows)
            # If we have since_date, merge with existing parquet
            if since_date and os.path.exists(out_path):
                df_existing = pd.read_parquet(out_path)
                df_existing = df_existing[df_existing["data"] < pd.Timestamp(since_date)]
                df = pd.concat([df_existing, df], ignore_index=True)
            df.to_parquet(out_path, index=False)
            date_range = f"{df['data'].min().strftime('%Y-%m-%d')} a {df['data'].max().strftime('%Y-%m-%d')}"
            print(f"  {folder_count} dias, {len(df)} linhas -> {out_path}")
            print(f"  Periodo: {date_range}")
            print(f"  Tamanho: {os.path.getsize(out_path) / 1024:.0f} KB")
        else:
            print(f"  Nenhum dado encontrado")


def copy_subfund_positions():
    """Copy posicoes_consolidado, posicoes_xml and posicoes_cvm from carteira_rv."""
    for fname in ["posicoes_consolidado.parquet", "posicoes_xml.parquet", "posicoes_cvm.parquet"]:
        src = os.path.join(CARTEIRA_RV_DATA, fname)
        dst = os.path.join(DATA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            size = os.path.getsize(dst) / 1024
            print(f"\n=== Copiado {fname} ({size:.0f} KB) ===")
        else:
            print(f"\n  {fname} nao encontrado em {CARTEIRA_RV_DATA}")


def supplement_blc4_positions():
    """Extract BLC4 positions for master CNPJs missing from posicoes_cvm.

    Some funds (e.g. Organon, Absolute Pace) are only available in CVM BLC4
    cache files, not in posicoes_cvm.parquet. This function extracts their
    stock positions from the BLC4 cache and appends to the deployed posicoes_cvm.
    """
    cache_dir = CARTEIRA_RV_CACHE
    if not os.path.isdir(cache_dir):
        print(f"\n  BLC4 cache nao encontrado: {cache_dir}")
        return

    # Load existing cvm data to find which masters are already covered
    cvm_path = os.path.join(DATA_DIR, "posicoes_cvm.parquet")
    existing_masters = set()
    if os.path.exists(cvm_path):
        df_cvm = pd.read_parquet(cvm_path)
        existing_masters = set(df_cvm["cnpj_fundo"].unique())

    # Find master CNPJs that are missing
    needed = {}  # master_cnpj -> [feeder_cnpj, ...]
    for feeder, master in MASTER_CNPJ_MAP.items():
        if master is None:
            continue
        # Check if master is in existing data
        if master in existing_masters:
            continue
        needed.setdefault(master, []).append(feeder)

    if not needed:
        print("\n  Todos os masters ja estao em posicoes_cvm.parquet")
        return

    print(f"\n=== Suplementando com BLC4 para {len(needed)} masters faltantes ===")
    for m, feeders in needed.items():
        feeder_names = [SUBFUNDO_NAMES.get(f, f) for f in feeders]
        print(f"  {m} -> {', '.join(feeder_names)}")

    # Format master CNPJs for matching
    def _fmt(c):
        c = c.zfill(14)
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}"

    master_formatted = {_fmt(m): m for m in needed.keys()}

    blc4_files = sorted(glob.glob(os.path.join(cache_dir, "cvm_blc4_*.parquet")), reverse=True)
    if not blc4_files:
        print("  Nenhum arquivo BLC4 encontrado")
        return

    # Also load PL data
    pl_data = {}
    rows = []
    found_masters = set()

    for blc4_file in blc4_files:
        if len(found_masters) == len(needed):
            break

        try:
            df_blc = pd.read_parquet(blc4_file)
        except Exception:
            continue

        cnpj_col = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in df_blc.columns else "CNPJ_FUNDO"
        if "TP_APLIC" not in df_blc.columns or "CD_ATIVO" not in df_blc.columns:
            continue

        mask_stocks = df_blc["TP_APLIC"].str.contains(
            r"(?:A.{1,3}es|Brazilian Depository)", case=False, na=False
        )
        mask_value = df_blc["VL_MERC_POS_FINAL"].fillna(0) > 0
        df_stocks = df_blc[mask_stocks & mask_value].copy()
        if df_stocks.empty:
            continue

        fname = os.path.basename(blc4_file)
        month_str = fname.replace("cvm_blc4_", "").replace(".parquet", "")
        try:
            ref_date = pd.Timestamp(f"{month_str[:4]}-{month_str[4:6]}-28")
        except Exception:
            continue

        # Load PL
        pl_file = os.path.join(cache_dir, f"cvm_pl_{month_str}.parquet")
        if os.path.exists(pl_file) and month_str not in pl_data:
            try:
                df_pl = pd.read_parquet(pl_file)
                pl_cnpj_col = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in df_pl.columns else "CNPJ_FUNDO"
                for _, row in df_pl.iterrows():
                    cnpj_val = str(row.get(pl_cnpj_col, ""))
                    vl_pl = row.get("VL_PATRIM_LIQ", 0)
                    if cnpj_val and vl_pl and vl_pl > 0:
                        pl_data[(cnpj_val, month_str)] = vl_pl
            except Exception:
                pass

        for fmt_cnpj, raw_master in master_formatted.items():
            if raw_master in found_masters:
                continue

            df_fund = df_stocks[df_stocks[cnpj_col] == fmt_cnpj]
            if df_fund.empty:
                continue

            found_masters.add(raw_master)
            fund_pl = pl_data.get((fmt_cnpj, month_str), 0)
            if fund_pl <= 0:
                fund_pl = df_fund["VL_MERC_POS_FINAL"].sum() * 1.05

            for _, row in df_fund.iterrows():
                ticker = str(row.get("CD_ATIVO", "")).strip()
                valor = float(row.get("VL_MERC_POS_FINAL", 0))
                if not ticker or valor <= 0:
                    continue
                pct = (valor / fund_pl * 100) if fund_pl > 0 else 0
                rows.append({
                    "cnpj_fundo": raw_master,
                    "data": ref_date,
                    "ativo": ticker,
                    "valor": valor,
                    "pl": fund_pl,
                    "pct_pl": pct,
                    "setor": "",
                    "fonte": "CVM_BLC4",
                })

    if not rows:
        print("  Nenhum dado BLC4 encontrado para masters faltantes")
        return

    df_supplement = pd.DataFrame(rows)
    print(f"  Extraidos {len(df_supplement)} registros de BLC4")
    for m in found_masters:
        n = len(df_supplement[df_supplement["cnpj_fundo"] == m])
        print(f"    {m}: {n} holdings")

    # Append to posicoes_cvm.parquet
    if os.path.exists(cvm_path):
        df_existing = pd.read_parquet(cvm_path)
        df_combined = pd.concat([df_existing, df_supplement], ignore_index=True)
    else:
        df_combined = df_supplement

    df_combined.to_parquet(cvm_path, index=False)
    size = os.path.getsize(cvm_path) / 1024
    print(f"  posicoes_cvm.parquet atualizado: {size:.0f} KB ({len(df_combined)} rows)")


# All CNPJs we need quotas for (sub-funds + Synta FIA + FIA II)
ALL_SUBFUND_CNPJS = list(SUBFUNDO_NAMES.keys())


def export_fund_quotas():
    """Export daily quotas for all sub-funds from CVM inf_diario cache into a single parquet."""
    cache_dir = CARTEIRA_RV_CACHE
    if not os.path.isdir(cache_dir):
        print(f"\n! Cache CVM nao encontrado: {cache_dir}")
        return

    inf_files = sorted(glob.glob(os.path.join(cache_dir, "cvm_inf_diario_*.parquet")))
    if not inf_files:
        print("\n! Nenhum arquivo cvm_inf_diario encontrado")
        return

    cnpj_set = set(ALL_SUBFUND_CNPJS)

    # Format CNPJs as xx.xxx.xxx/xxxx-xx for matching CVM format
    def _fmt(c):
        c = c.zfill(14)
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}"

    fmt_to_raw = {_fmt(c): c for c in cnpj_set}
    frames = []

    for fpath in inf_files:
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            continue

        # Determine CNPJ column
        cnpj_col = None
        for c in ["cnpj_norm", "CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"]:
            if c in df.columns:
                cnpj_col = c
                break
        dt_col = "DT_COMPTC"
        vl_col = "VL_QUOTA"
        if cnpj_col is None or dt_col not in df.columns or vl_col not in df.columns:
            continue

        # Filter for our CNPJs
        if cnpj_col == "cnpj_norm":
            mask = df[cnpj_col].isin(cnpj_set)
        else:
            mask = df[cnpj_col].isin(fmt_to_raw.keys())

        df_f = df[mask].copy()
        if df_f.empty:
            continue

        df_f["data"] = pd.to_datetime(df_f[dt_col])
        if cnpj_col == "cnpj_norm":
            df_f["cnpj_raw"] = df_f[cnpj_col]
        else:
            df_f["cnpj_raw"] = df_f[cnpj_col].map(fmt_to_raw)
        df_f["nome"] = df_f["cnpj_raw"].map(SUBFUNDO_NAMES)
        df_f["quota"] = pd.to_numeric(df_f[vl_col], errors="coerce")
        frames.append(df_f[["data", "cnpj_raw", "nome", "quota"]].dropna())

    if not frames:
        print("\n! Nenhuma cota encontrada para os sub-fundos")
        return

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values("data").drop_duplicates(subset=["data", "cnpj_raw"], keep="last")

    out_path = os.path.join(DATA_DIR, "fund_quotas.parquet")
    result.to_parquet(out_path, index=False)
    n_funds = result["cnpj_raw"].nunique()
    n_days = result["data"].nunique()
    size = os.path.getsize(out_path) / 1024
    print(f"\n=== Exportando cotas dos sub-fundos ===")
    print(f"  {n_funds} fundos, {n_days} dias, {len(result)} linhas -> {out_path}")
    print(f"  Periodo: {result['data'].min().date()} a {result['data'].max().date()}")
    print(f"  Tamanho: {size:.0f} KB")


def main():
    parser = argparse.ArgumentParser(description="Exportar dados XMLs para parquets")
    parser.add_argument("--since", type=str, help="Data inicio (YYYY-MM-DD)")
    args = parser.parse_args()

    since_date = None
    if args.since:
        since_date = datetime.strptime(args.since, "%Y-%m-%d").date()

    if not os.path.isdir(XML_BASE):
        print(f"ERRO: Diretorio XML nao encontrado: {XML_BASE}")
        sys.exit(1)

    print(f"Diretorio XML: {XML_BASE}")
    print(f"Diretorio output: {DATA_DIR}")
    if since_date:
        print(f"Exportando desde: {since_date}")

    export_synta_timeseries(since_date)
    copy_subfund_positions()
    supplement_blc4_positions()
    export_fund_quotas()

    print("\nExportacao concluida!")
    print(f"Arquivos em {DATA_DIR}:")
    for f in sorted(os.listdir(DATA_DIR)):
        fp = os.path.join(DATA_DIR, f)
        print(f"  {f} ({os.path.getsize(fp) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

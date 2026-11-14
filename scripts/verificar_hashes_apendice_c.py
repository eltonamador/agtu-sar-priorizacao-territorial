"""Verifica os sete identificadores do Apêndice C; sem dependências e sem escrita."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys


CASOS = {
    "urbe01": "490663d2459b1aa5fac151b425ff474c0dacdb44891ee8530b2dd9960dbdcb23",
    "rural01": "d51dd9e3252f50bd1d756b4b9ee914aca0b7300eda6e2b2f751e5f6fa587301e",
    "mata01": "7ba1186d90aaf5ef6b92dd7095727e151c948880163b3c81d0c4cd7ff02df29b",
}
RANKINGS = {
    "campo_mata02_mzg2/ensaio_complementar_v2_249/ranking_BASE_completo.json":
        "8236e5244a8f6fef501d4aea9492c56bf75d34a87109eecfc94da03e681f31fb",
    "campo_mata03_km21/ranking_BASE.json":
        "1ba965b3d69f07e06607771036d8246dc6023886929d2a6ca3c6340d5094e11a",
}
PROJECAO = "bff2deb9cf329096d7191b86381d5570c2df6905ba51499242d51c07531053dc"
PACOTE = "0d90933c35117cf6abc62346ec790e38328c65fa9af9f94752a8554286cbc837"


def arquivo(p):
    digest = hashlib.sha256()
    with p.open("rb") as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def canonico(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def ler(p):
    return json.loads(p.read_text(encoding="utf-8"))


def verificar(rotulo, calculado, esperado, registrado=None):
    confere = calculado == esperado and (registrado is None or calculado == registrado)
    print(f'{"CONFERE" if confere else "NÃO CONFERE"} | {rotulo} | {calculado}')
    if not confere:
        print(f'  esperado={esperado}; manifesto={registrado}')
    return confere


def comparar(raiz):
    verificacoes = []
    for caso, esperado in CASOS.items():
        s = raiz / "work" / f"{caso}_processamento_cego_v1" / f"run_{caso}_blind.py"
        d = raiz / "outputs" / f"campo_{caso}" / "processamento_cego_v1"
        lista = next(ast.literal_eval(n.value) for n in ast.parse(s.read_text(encoding="utf-8")).body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                     t.id == 'SCIENTIFIC_FILES' for t in n.targets))
        m = ler(d / "manifesto_processamento_cego.json")
        individuais = {n: arquivo(d / n) for n in lista}
        declarados = {Path(x["path"]).name: x["sha256"] for x in m["files"] if x["role"] == "output"}
        for n, val in individuais.items():
            if declarados.get(n) != val:
                raise ValueError(f"{caso}: manifesto individual divergente para {n}")
        verificacoes.append(verificar(f"{caso}: {len(lista)} arquivos", canonico(individuais),
                                      esperado, m["scientific_projection_sha256"]))
    for relativo, esperado in RANKINGS.items():
        verificacoes.append(verificar(relativo, arquivo(raiz / "outputs" / relativo), esperado))
    d = raiz / "outputs/ext_espacial_s3_setorizacao_priorizacao_v1_1/results"
    m = ler(d / "manifest_setorizacao_dev.json")
    linhas = ler(d / "sector_results_dev.json")["results"]
    campos = ("sector_id", "score_base", "rank_base_within_buffer", "decision_status",
              "selected_sector", "top1_stability")
    projecao = [{c: r["buffer_decision_status" if c == "decision_status" else c] for c in campos}
                for r in linhas]
    verificacoes.append(verificar(f"DEV-S: projeção de {len(linhas)} setores", canonico(projecao),
                                  PROJECAO, m["scientific_projection_sha256"]))
    pacote = {}
    for item in m["files"]:
        if item["role"] == "output":
            nome = Path(item["path"]).name
            pacote[nome] = arquivo(d / nome)
            if pacote[nome] != item["sha256"]:
                raise ValueError(f"DEV-S: manifesto individual divergente para {nome}")
    verificacoes.append(verificar(f"DEV-S: pacote de {len(pacote)} saídas", canonico(pacote),
                                  PACOTE, m["scientific_bundle_sha256"]))
    print(f"{sum(verificacoes)}/{len(verificacoes)} identificadores conferem")
    return 0 if all(verificacoes) and len(verificacoes) == 7 else 1


if __name__ == "__main__":
    par = argparse.ArgumentParser(description=__doc__)
    par.add_argument("raiz", nargs="?", type=Path, default=Path(__file__).resolve().parents[1],
                     help="raiz contendo work/ e outputs/ (padrão: raiz deste pacote)")
    try:
        sys.exit(comparar(par.parse_args().raiz))
    except (OSError, ValueError, KeyError, StopIteration) as e:
        print(f"Verificação incompleta: {e}", file=sys.stderr)
        sys.exit(2)

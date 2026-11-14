"""Executa o verificador original DEV-S; relocaliza apenas os caminhos históricos."""
import importlib.util, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=root/'work/ext_espacial_setores_v1_1/verify_setorizacao_priorizacao.py'
spec=importlib.util.spec_from_file_location('verificador_preservado',source)
v=importlib.util.module_from_spec(spec);sys.modules[spec.name]=v;spec.loader.exec_module(v)
original=v.resolve_manifest_path
def local(raw,manifest):
    p=Path(str(raw))
    if not p.is_absolute():return original(raw,manifest)
    candidates=[i for i,x in enumerate(p.parts) if x in ('work','outputs')]
    if not candidates:raise ValueError('Caminho absoluto fora das raízes científicas: '+p.name)
    target=(root/Path(*p.parts[candidates[-1]:])).resolve()
    if not target.is_relative_to(root):raise ValueError('Caminho fora do pacote')
    return target
v.resolve_manifest_path=local
sys.exit(v.main(sys.argv[1:]))

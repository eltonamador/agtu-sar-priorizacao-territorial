#!/bin/bash
# Usar na raiz que contém work/ e outputs/. Cria somente cópias temporárias.
set -eu
root=$(pwd -P)
base_python=${PYTHON:-python3}
test_area=$(mktemp -d)
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 LC_ALL=C
unset PYTHONPATH PYTHONHOME
mods=(ext_espacial_buffer_v1 ext_espacial_setores_v1_1 rural01_mov_v2 mata01_mov_v1 perfil_vitima_v3 protocolo_integrado_v1)
mkdir -p "$test_area/work" "$test_area/outputs"
for m in "${mods[@]}"; do
    mkdir -p "$test_area/work/$m"
    find "$root/work/$m" -maxdepth 1 -type f -exec cp {} "$test_area/work/$m/" \;
done
for m in modulo_perfil_vitima_v3 protocolo_integrado_v1; do
    cp -R "$root/outputs/$m" "$test_area/outputs/"
done
"$base_python" -m venv "$test_area/venv"
py="$test_area/venv/bin/python"
date -u
uname -srm
"$py" -VV
"$py" -m pip --version
echo 'pip freeze (nenhuma linha = nenhum pacote adicional)'
"$py" -m pip freeze
echo 'pip freeze --all'
"$py" -m pip freeze --all
if command -v swift >/dev/null; then swift --version; fi
echo "Cópia de execução: $test_area"
result=0
for m in "${mods[@]}"; do
    echo "MÓDULO $m"
    (cd "$test_area/work/$m" && "$py" -m unittest discover -v -s . -p 'test*.py') || result=1
done
echo 'PACOTE INTEGRADO: execução adicional tal como build_release.py combina as suítes; NÃO somar aos testes distintos.'
(cd "$test_area" && "$py" -c 'import sys,unittest,pathlib; w=pathlib.Path("work").resolve(); p=w/"protocolo_integrado_v1"; sys.path.insert(0,str(p)); suite=unittest.TestSuite([unittest.TestLoader().discover(str(p),pattern="test*.py"),unittest.TestLoader().discover(str(w/"perfil_vitima_v3"),pattern="test_profile*.py")]); sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())') || result=1
echo 'CONFERÊNCIA DEV-S (separada dos testes unitários)'
s="$root/work/ext_espacial_setores_v1_1"
b="$root/work/ext_espacial_buffer_v1/results"
"$py" "$root/scripts/verificar_dev_local.py" --results-dir "$s/results" --buffer-json "$b/buffer_results_dev.json" --buffer-geojson "$b/buffer_polygons_dev.geojson" --config "$s/config_setorizacao_priorizacao_v1_1.json" --report "$test_area/verificacao_DEV-S.json" || result=1
echo 'SUÍTES COMPLEMENTARES E HISTÓRICAS EM WORK: isoladas da Tabela 8, sem testes de dependências de terceiros nem cópias de distribuição.'
shopt -s nullglob
for dir in "$root"/work/*/; do
  tests=("$dir"/test_*.py); [ ${#tests[@]} -gt 0 ] || continue
  m=$(basename "$dir")
  case " ${mods[*]} " in *" $m "*) continue;; esac
  mkdir -p "$test_area/work/$m"
  find "$dir" -maxdepth 1 -type f -exec cp {} "$test_area/work/$m/" \;
done
for m in modulo_perfil_vitima_v2 campo_rural01 campo_urbe01 campo_mata01; do
  cp -R "$root/outputs/$m" "$test_area/outputs/"
done
# A cópia pública não contém originais fotográficos. Somente mediante pedido
# explícito do operador, aportar ao diretório temporário o lote de custódia.
photo_src="$root/casos/URBE-01/fotos/originais"
if [ "${COM_CUSTODIA:-0}" = 1 ]; then
    [ -d "$photo_src" ] || { echo 'Lote fotográfico privado URBE-01 ausente'; exit 2; }
    mkdir -p "$test_area/outputs/campo_urbe01/reservado_originais"
    find "$photo_src" -type f \( -iname '*.jpg' -o -iname '*.heic' \) -exec cp {} "$test_area/outputs/campo_urbe01/reservado_originais/" \;
fi
geodata=sprint2_s2_06_geo05_v33
mkdir -p "$test_area/outputs/$geodata"
for f in "$root/outputs/$geodata"/osm_*_raw.json "$root/outputs/$geodata"/*.hgt.gz "$root/outputs/$geodata"/worldcover_tiles; do cp -R "$f" "$test_area/outputs/$geodata/"; done
# Dependências opcionais do acervo histórico, não da Tabela 8. Copiar distribuições
# instaladas do mesmo Python base quando disponíveis, sem rede nem system-site-packages.
sp=$("$py" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
bp=$("$base_python" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
for f in "$bp"/{et_xmlfile,openpyxl,PIL,reportlab,charset_normalizer} "$bp"/{et_xmlfile,openpyxl,pillow,reportlab,charset_normalizer}-*.dist-info; do
    if [ -e "$f" ]; then cp -R "$f" "$sp/"; fi
done
echo 'pip freeze complementar (somente suítes extras)'
"$py" -m pip freeze
for dir in "$test_area"/work/*/; do
  m=$(basename "$dir")
  case " ${mods[*]} " in *" $m "*) continue;; esac
  if [ "$m" = urbe01_auditoria_visual_v1 ] && [ "${COM_CUSTODIA:-0}" != 1 ]; then
      echo "FORA DO MODO PÚBLICO: $m (3 testes de fotografias sob custódia)."
      continue
  fi
  echo "EXTRA $m"
  (cd "$dir" && "$py" -m unittest discover -v -s . -p 'test_*.py') || result=1
done
exit "$result"

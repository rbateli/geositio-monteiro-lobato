#!/usr/bin/env bash
# Deploy do GeoSítio no GitHub Pages (branch gh-pages orphan, force-push).
# Histórico da gh-pages = sempre 1 commit. master nunca é poluído com o HTML de 14 MB.
#
# Uso: bash deploy.sh

set -euo pipefail

cd "$(dirname "$0")"

# 1. Regerar o site
echo "==> Regerando site (python gerar_site.py)..."
.venv/Scripts/python.exe gerar_site.py

if [ ! -f data/sitio.html ]; then
  echo "ERRO: data/sitio.html nao foi gerado. Abortando."
  exit 1
fi

TAMANHO=$(du -h data/sitio.html | cut -f1)
echo "==> Site gerado: data/sitio.html ($TAMANHO)"

# 2. Preparar worktree isolada em /tmp pra branch gh-pages
WORKTREE=".gh-pages-worktree"

# Limpa worktree antiga se existir
if [ -d "$WORKTREE" ]; then
  git worktree remove --force "$WORKTREE" 2>/dev/null || rm -rf "$WORKTREE"
fi

# Cria branch gh-pages orphan via worktree (sem histórico anterior)
echo "==> Criando branch gh-pages orphan..."
git worktree add --detach "$WORKTREE"
(
  cd "$WORKTREE"
  # Garante que não exista branch local gh-pages do deploy anterior
  git branch -D gh-pages 2>/dev/null || true
  git checkout --orphan gh-pages
  git rm -rf . 2>/dev/null || true
  cp ../data/sitio.html ./index.html
  cp ../data/thumb_agua.png ./thumb_agua.png
  # .nojekyll impede o Jekyll do GitHub Pages de processar arquivos com _underscore
  touch .nojekyll
  git add index.html thumb_agua.png .nojekyll
  git commit -m "deploy: sitio $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push -f origin gh-pages
)

# 3. Limpa worktree
git worktree remove --force "$WORKTREE"

echo ""
echo "==> Deploy concluido."
echo "   URL: https://rbateli.github.io/geositio-monteiro-lobato/"
echo "   (pode levar ~1 min pra propagar)"

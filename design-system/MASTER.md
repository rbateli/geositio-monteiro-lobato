# GeoSítio — Design System (MASTER)

Fonte da verdade para decisões visuais e de UX do relatório/portfólio GeoSítio.
Aplicável a todas as páginas geradas por `gerar_site.py` e artefatos HTML em `data/`.

> **Regra de herança:** se existir um arquivo em `design-system/pages/<pagina>.md`, as regras dele sobrescrevem este MASTER para aquela página. Caso contrário, este MASTER é exclusivo.

---

## 1. Contexto e princípios

- **Produto:** relatório geoespacial + portfólio de ciência de dados aplicada a propriedade rural (3,3 ha, Monteiro Lobato/SP).
- **Público duplo:**
  1. Pai do Rafael — leigo, precisa entender recomendações práticas (onde plantar, pastagem, tanque, erosão).
  2. Recrutador técnico — avalia qualidade analítica, apresentação e clareza.
- **Plataforma:** HTML puro estático + Plotly.js + Leaflet. Sem Streamlit.
- **Princípios:**
  1. **Clareza antes de sofisticação.** Termos técnicos sempre explicados inline.
  2. **Dados em destaque, decoração a serviço.** Nada de gradiente/sombra que atrapalhe leitura.
  3. **Consistência visual total.** Mesma paleta, tipografia e espaçamento em todas as páginas.
  4. **Recomendações baseadas em dados.** Nunca sugerir genérico; sempre citar o número (inclinação, NDVI, etc.).

## 2. Estilo

**Editorial Natural + Data Storytelling.** Tipografia forte tipo editorial (Stripe docs / Linear / Every.to) com paleta terrosa discreta que evoca tema rural sem clichê.

Evitar: glassmorphism, neon, brutalism, SaaS genérico azul-roxo, templates de dashboard prontos.

## 3. Tokens de cor (modo claro)

```css
:root {
  /* Superfícies */
  --bg:         #FAF8F3;  /* off-white terroso */
  --surface:    #FFFFFF;  /* cards */
  --surface-2:  #F1EDE4;  /* seções alternadas */
  --border:     #E4DED1;  /* divisores suaves */

  /* Texto */
  --ink:        #1E2A1F;  /* primário (verde-escuro quase preto) */
  --ink-2:      #4A5A4D;  /* secundário */
  --muted:      #8A8578;  /* legendas, hints */

  /* Marca / ação */
  --primary:    #2F6B3A;  /* verde-mata — CTA, links */
  --primary-ink:#1B4223;  /* hover/pressed */
  --accent:     #C97B3F;  /* terra/ocre — destaques secundários */

  /* Semânticos */
  --warn:       #D4A017;  /* atenção — declividade média */
  --danger:     #B84A3E;  /* erosão, risco */
  --success:    #2F6B3A; /* reutiliza primary */
}
```

Contraste `--ink` em `--bg` ≈ 13:1 (AAA). Estados `hover` escurecem 1 tom; `disabled` usa opacity 0.45.

**Paleta de dados Plotly** (para séries/categorias em gráficos):

```
#2F6B3A  #C97B3F  #4A7FA8  #7A8C4E  #B84A3E  #8A5A9C  #D4A017  #4A5A4D
```

Nunca usar somente cor para transmitir significado — sempre combinar com ícone, rótulo ou padrão.

## 4. Tipografia

- **Display/Heading:** `Fraunces` (Google Fonts, serif variável, opsz+wght)
- **Body/UI:** `Inter` (Google Fonts, sans variável)
- **Mono/dados:** `JetBrains Mono` (tabular figures)

Escala: `12 · 14 · 16 · 18 · 22 · 28 · 36 · 48` (rem base 16px).
Line-height: 1.6 no corpo, 1.2 nos títulos.
Números em estatísticas: `font-variant-numeric: tabular-nums`.

Pesos: Fraunces 500/600/700 para títulos; Inter 400 corpo, 500 labels, 600 CTAs.

## 5. Espaçamento e layout

- Escala: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96`.
- Container: `max-width: 960px` para texto; `max-width: 1200px` para blocos de mapa/dashboard.
- Gutters: 16px mobile, 24px tablet, 32px desktop.
- Breakpoints: `640 / 768 / 1024 / 1440`.
- Mobile-first. Sem scroll horizontal.
- Grid de gráficos: 2 colunas em desktop, stack em mobile.

## 6. Componentes

### 6.1 Hero editorial
- Título em Fraunces 48px, subtítulo Inter 18px, 1–2 linhas explicando o que é o relatório.
- Fundo: mapa estático ou foto com overlay `rgba(30, 42, 31, 0.55)` para legibilidade.
- CTA opcional "Ver mapa interativo" com scroll suave.

### 6.2 Card de estatística
- Ícone Lucide SVG 20×20 à esquerda em `--primary`.
- Label caps pequena (11px, tracking 0.08em) em `--muted`.
- Número grande Fraunces 36px com tabular figures.
- Descrição curta abaixo em Inter 14px `--ink-2`.
- Padding 24px, borda 1px `--border`, radius 12px, background `--surface`.

### 6.3 Glossário inline
- Termo técnico (NDVI, SRTM, Sentinel-2, EMBRAPA) aparece sublinhado em tracejado com `abbr` ou botão toggle.
- Clique/hover exibe tooltip com 1–2 frases de explicação leiga.
- Antes da primeira aparição numa seção, parágrafo "O que é isso?" com explicação expandida.

### 6.4 Mapa com legenda dinâmica
- Leaflet. Controle de camadas visível (não recolhido).
- Painel lateral direito (`width: 280px`) muda conforme camada ativa:
  - NDVI → escala de cor + interpretação (vermelho = solo exposto/seco, verde = vegetação densa).
  - Declividade → classes EMBRAPA + recomendação.
- Sem camadas SRTM 30m (decisão anterior, pixelado demais para 3.3 ha).
- Em mobile: legenda vira acordeão abaixo do mapa.

### 6.5 Gráfico Plotly
- Tema claro custom, sem gridlines fortes (`gridcolor: #E4DED1`).
- Fonte Inter 12px nos eixos.
- Tooltip rico com unidade e contexto.
- Paleta de dados definida em §3.
- Título em Fraunces 22px acima, não dentro do gráfico.
- Respeitar `prefers-reduced-motion`.

### 6.6 Card de recomendação por zona
- Nome da zona (ex: "Zona A — Meia Encosta Norte") em Fraunces 22px.
- Badge com declividade média e classe EMBRAPA.
- Parágrafo: "Esta zona tem inclinação X%, por isso é adequada para Y."
- Ícone da cultura/uso recomendado.
- Cor de borda esquerda (4px) conforme aptidão: verde (alta), ocre (média), vermelho (restrita).

## 7. Iconografia

- Biblioteca única: **Lucide** (via CDN ou inline SVG).
- Traço 1.5px, tamanhos `16 · 20 · 24`.
- Nunca usar emoji como ícone estrutural (apenas como ornamento opcional em texto corrido).
- Cor: `currentColor`, herda do contexto.

## 8. Interação e movimento

- Transições 150–250ms, easing `cubic-bezier(0.4, 0, 0.2, 1)`.
- Hover em cards: elevação sutil (`box-shadow` leve) + translateY(-2px).
- Focus ring visível 2px `--primary` com offset 2px.
- Respeitar `prefers-reduced-motion: reduce` desabilitando transições não essenciais.

## 9. Acessibilidade (checklist obrigatório)

- [ ] Contraste AA em todo texto (4.5:1 corpo, 3:1 títulos grandes).
- [ ] Todo ícone funcional tem `aria-label`.
- [ ] Ordem de foco segue ordem visual.
- [ ] Imagens de mapa/gráfico têm `alt` ou `aria-describedby` apontando para tabela/texto alternativo.
- [ ] Cor nunca é o único indicador (sempre acompanhada de ícone ou rótulo).
- [ ] Tipografia responde a zoom 200% sem quebrar layout.

## 10. Anti-patterns

- Emoji como ícone de navegação/estrutura.
- Plotly default azul/laranja.
- Gridlines pretas fortes ou fundos de gráfico cinza.
- Termos técnicos sem explicação inline.
- Camadas SRTM 30m visíveis no mapa.
- Gradientes chamativos, sombras pesadas, neon.
- Texto em cima de imagem sem overlay de contraste.
- Streamlit (decisão anterior).

## 11. Implementação

- Todo CSS mora como `<style>` embutido no HTML gerado por `gerar_site.py` (sem dependência externa além de Google Fonts e CDNs de Plotly/Leaflet/Lucide).
- Fontes carregadas com `font-display: swap`.
- Tokens em `:root` como CSS variables — mudança central.
- Reset mínimo (box-sizing, margin reset).
- Dark mode: fora de escopo na v1. Projetar pares light/dark só quando a v1 estiver estável.

---

_Última revisão: 2026-04-14._

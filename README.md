# GEO Auditor

**Diagnóstico automatizado de visibilidade em Motores de IA (GEO)**

[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## O que e GEO Auditor?

Uma ferramenta que **mede e diagnostica** o quao preparado seu site esta para ser **citado como fonte** por motores de IA como:

| Motor | Exemplo de citacao |
|-------|-------------------|
| **ChatGPT** | "Segundo o site X, a energia solar em Goiania custa..." |
| **Perplexity** | Lista de fontes ao final da resposta |
| **Gemini (Google)** | Respostas com links contextuais |
| **Claude (Anthropic)** | Citacoes diretas durante raciocinio |

> **Atencao:** Este auditor e especializado em **Generative Engine Optimization (GEO)**. Para SEO tradicional no Google, utilize ferramentas como [Google Search Console](https://search.google.com/search-console) ou [PageSpeed Insights](https://pagespeed.web.dev).

---

## O que o sistema analisa?

### 12 sinais tecnicos de prontidao para IA

| Categoria | Sinal | Peso |
|-----------|-------|------|
| **Acessibilidade IA** | Bots de IA liberados (robots.txt) | 3 |
| | Arquivo llms.txt publicado | 1 |
| | Sitemap.xml acessivel | 1 |
| **Dados Estruturados** | Schema LocalBusiness (JSON-LD) | 3 |
| | Schema FAQPage | 3 |
| | Schema Organization | 1 |
| **Conteudo** | Secao de FAQ visivel | 2 |
| | Headings em formato de pergunta | 2 |
| | Citacoes geograficas (cidade/regiao) | 2 |
| **NAP (Contato)** | Telefone visivel | 2 |
| | Endereco com CEP | 1 |
| **Meta** | Meta description adequada (50-170 chars) | 1 |

**Pontuacao maxima:** 22 pontos

---

## Funcionalidades

### Interface Streamlit
- Painel de metricas visual
- Matriz competitiva com heatmap interativo (Plotly)
- Velocimetro de pontuacao de prontidao
- Grafico de barras por categoria

### Crawler inteligente
- Mapeamento automatico de ate 6 paginas por site
- Descoberta via sitemap.xml + links internos
- **Suporte a SPAs (React/Vue)** via Playwright (opcional)
- Rate limiting e cache para eficiencia

### Medicao de Share of Voice (SOV)
- Percentual de citacoes do cliente vs concorrentes
- Segmentado por tipo de busca (branded, local, informacional, comparativa)
- Identificacao dos dominios que mais aparecem no lugar do cliente

### Plano de acao priorizado
- Matriz **impacto x esforco** (alto/trivial, medio/baixo, etc.)
- Gaps de conteudo: perguntas que concorrentes respondem e voce nao
- Ordenacao automatica por prioridade

### Geracao automatica de JSON-LD
- Blocos prontos para copiar/colar no site
- Inclui: LocalBusiness, Organization, FAQPage, Service
- Marcado com instrucoes de onde instalar cada bloco

### Relatorio profissional
- Formato HTML responsivo (pronto para impressao)
- Download em PDF (via WeasyPrint)
- Preview embutido na interface

---

## Instalacao e Uso

### Requisitos
- Python 3.10+
- Pip

### Instalacao rapida

```bash
git clone https://github.com/seu-usuario/geo-auditor.git
cd geo-auditor
python launch.py --mode install
python launch.py --mode streamlit
# Acesse http://localhost:8501
```

### Modos de execucao

| Comando | Descricao |
|---------|-----------|
| `python launch.py --mode streamlit` | Interface web (padrao) |
| `python launch.py --mode cli --domain x.com` | Diagnostico via linha de comando |
| `python launch.py --mode cli --domain x.com --output diag.json` | Salva resultado em JSON |
| `python launch.py --mode docker` | Gera Dockerfile + docker-compose.yml |
| `python launch.py --mode install` | Instala dependencias e Playwright |

### Opcoes de linha de comando

```bash
# Streamlit
--port 8501              # Porta do servidor
--no-browser             # Nao abrir navegador automaticamente

# CLI
--domain x.com           # Dominio obrigatorio
--output diag.json       # Arquivo de saida (opcional)
--no-install             # Pular instalacao de dependencias
```

---

## Docker

```bash
python launch.py --mode docker
docker-compose build
docker-compose up
# Acesse http://localhost:8501
```

---

## Estrutura do Projeto

```
geo_auditor/
├── app.py                 # Interface Streamlit (principal)
├── launch.py              # Launcher universal (CLI + Docker)
├── requirements.txt       # Dependencias Python
├── geo.db                 # Banco SQLite (cache de concorrentes)
├── Dockerfile             # Gerado via --mode docker
├── docker-compose.yml     # Gerado via --mode docker
└── README.md              # Este arquivo
```

---

## Dependencias principais

| Pacote | Versao | Uso |
|--------|--------|-----|
| streamlit | >=1.28.0 | Interface web |
| requests | >=2.31.0 | Requisicoes HTTP |
| beautifulsoup4 | >=4.12.0 | Parsing de HTML |
| plotly | >=5.17.0 | Graficos interativos |
| pandas | >=2.0.0 | Manipulacao de dados |
| weasyprint | >=60.0 | Geracao de PDF |
| playwright | >=1.40.0 | Crawl de SPAs (opcional) |
| click | >=8.1.0 | CLI parsing |

---

## Modo Demo

Sem API key? Selecione **"Modo Demo"** na interface para testar todas as funcionalidades com dados simulados do dominio `mdaenergiasolar.com.br`.

**O que funciona no Demo:**
- Diagnostico completo
- Heatmap e graficos
- Geracao de JSON-LD
- Download de relatorio

**O que NAO funciona:**
- Crawler real (usa dados pre-calculados)
- Medicao via Perplexity API

---

## Exemplo de Relatorio

O relatorio gerado contem:

1. **Veredito** — Score percentual e interpretacao
2. **Share of Voice** — Frequencia de citacao por tipo de busca
3. **Matriz competitiva** — Heatmap dos 12 sinais (voce vs concorrentes)
4. **Plano de acao** — Recomendacoes priorizadas por impacto x esforco
5. **Gaps de conteudo** — Perguntas que concorrentes respondem
6. **Anexo tecnico** — Blocos JSON-LD prontos para instalacao

---

## Limitacoes Conhecidas

| Limitacao | Impacto | Mitigacao |
|-----------|---------|-----------|
| **Nao cobre SEO Google** | Alto | Use ferramentas especificas (GSC, PageSpeed) |
| **Nao mede backlinks** | Medio | Use Ahrefs/SEMrush |
| **Nao analisa Core Web Vitals** | Medio | Use PageSpeed Insights |
| **API Perplexity requer chave paga** | Medio | Use modo Demo ou contrate chave |
| **Crawl limitado a 6 paginas** | Baixo | Configuravel via `max_pages_per_site` |

---

## Roadmap (Futuro)

- [ ] Modulo opcional de SEO Google (PageSpeed + GSC basico)
- [ ] Exportacao para Google Sheets
- [ ] Agendamento de auditorias recorrentes
- [ ] Webhook para notificacoes
- [ ] Suporte a mais motores de IA (Copilot, You.com)

---

## Contribuicao

Contribuicoes sao bem-vindas! Siga os passos:

1. Fork o projeto
2. Crie sua branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudancas (`git commit -m 'feat: adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

---

## Licenca

MIT

---

## Contato

- **Autor:** Romel
- **Telefone:** 62 99299-1555

---

## Agradecimentos

- [Streamlit](https://streamlit.io) — Framework da interface
- [Plotly](https://plotly.com) — Visualizacoes interativas
- [Playwright](https://playwright.dev) — Crawl de SPAs
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — Parsing HTML

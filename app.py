#!/usr/bin/env python3
"""
GEO Auditor MVP — app.py
========================
Interface web unificada (Streamlit) que orquestra o pipeline completo:
  Fase 0 (measure) -> Fase 1 (diagnose) -> Fase 2 (schema) -> Fase 3 (report)

Gera laudo HTML/PDF pronto para entrega ao cliente.
Modo demo disponível para apresentações sem API key.
"""

import streamlit as st
import os
import sys
import json
import ipaddress
import sqlite3
import re
import time
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone
from collections import Counter
from html import escape
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="GEO Auditor — Visibilidade em Motores de IA",
    page_icon="\U0001f50d",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CSS CUSTOMIZADO — estética de laudo técnico
# =============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=IBM+Plex+Mono:wght@400;600&display=swap');

:root {
    --solar: #E8930C;
    --ink: #15191C;
    --muted: #5C6670;
    --line: #E3E1DB;
    --panel: #F4F4F1;
    --ok: #1F7A4D;
    --fail: #C03B2D;
}

/* Header e títulos */
.stApp header {background: transparent;}
h1, h2, h3 {
    font-family: 'Archivo', system-ui, sans-serif !important;
    letter-spacing: -0.01em;
}
.eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--solar);
    margin-bottom: 6px;
}

/* Métricas */
.metric-card {
    background: var(--panel);
    border-left: 4px solid var(--solar);
    padding: 20px 24px;
    border-radius: 0 8px 8px 0;
    margin: 10px 0;
}
.metric-big {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 48px;
    font-weight: 600;
    line-height: 1;
    color: var(--ink);
}
.metric-big small {
    font-size: 20px;
    color: var(--muted);
}

/* Botões */
.stButton>button {
    background: var(--ink) !important;
    color: white !important;
    font-family: 'Archivo', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 6px !important;
    padding: 12px 28px !important;
    border: none !important;
    transition: all 0.2s;
}
.stButton>button:hover {
    background: var(--solar) !important;
    color: var(--ink) !important;
    transform: translateY(-1px);
}

/* Progresso */
.stProgress > div > div {
    background: var(--solar) !important;
}

/* Tabelas */
.dataframe {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
}
.dataframe th {
    background: var(--ink) !important;
    color: white !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 11px;
}
.dataframe td {
    border-bottom: 1px solid var(--line) !important;
}

/* Badges */
.badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 3px;
    margin-right: 6px;
}
.badge-impacto-alto {background: var(--fail); color: white;}
.badge-impacto-medio {background: var(--solar); color: var(--ink);}
.badge-impacto-baixo {background: var(--line); color: var(--ink);}
.badge-esforco-trivial {background: var(--ok); color: white;}
.badge-esforco-baixo {background: #2a9d8f; color: white;}
.badge-esforco-medio {background: var(--line); color: var(--ink);}

/* Cards de recomendação */
.rec-card {
    background: white;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 16px 20px;
    margin: 8px 0;
    transition: box-shadow 0.2s;
}
.rec-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.rec-num {
    font-family: 'IBM Plex Mono', monospace;
    color: var(--solar);
    font-weight: 600;
    font-size: 18px;
    margin-right: 10px;
}

/* Anexo técnico */
.code-block {
    background: var(--panel);
    border-radius: 8px;
    padding: 16px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    line-height: 1.5;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
    border: 1px solid var(--line);
}

/* Footer */
.report-footer {
    border-top: 3px solid var(--ink);
    margin-top: 40px;
    padding-top: 20px;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# CONSTANTES E CONFIGURAÇÕES
# =============================================================================
DEFAULT_CONFIG = {
    "client": {
        "domain": "mdaenergiasolar.com.br",
        "name_variants": ["Mundo Automação Energia Solar", "Mundo Automação", "MDA Energia Solar"],
    },
    "geo_terms": ["Goiânia", "Goiás", "Aparecida de Goiânia"],
    "competitors": [],
    "max_competitors": 5,
    "max_pages_per_site": 6,
    "delay_s": 1.0,
}

IGNORE_DOMAINS = {
    "youtube.com", "facebook.com", "instagram.com", "linkedin.com",
    "wikipedia.org", "pt.wikipedia.org", "reclameaqui.com.br",
    "reddit.com", "quora.com", "gov.br", "x.com", "twitter.com",
    "tiktok.com", "mercadolivre.com.br", "olx.com.br",
}

AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
           "Perplexity-User", "ClaudeBot", "Claude-User", "anthropic-ai",
           "Google-Extended", "CCBot", "Amazonbot", "meta-externalagent"]

HEADERS = {"User-Agent": ("Mozilla/5.0 (compatible; GEOAuditor/1.0; "
                          "+https://example.com/bot)")}

MIN_TEXT_LEN = 400
REQUEST_TIMEOUT = 12
INTERESTING_PATHS = ["servic", "energia", "solar", "faq", "pergunta", "sobre",
                     "quem-somos", "contato", "orcament", "preco", "blog",
                     "automacao", "residencial", "empresarial"]

JSONLD_REQUIRED = {
    "LocalBusiness": ["name", "address", "telephone", "url"],
    "Organization":  ["name", "url"],
    "FAQPage":       ["mainEntity"],
}

QUESTION_START = re.compile(
    r"^(como|quanto|qual|quais|onde|por\s*que|porque|o\s*que|quando|"
    r"vale\s*a\s*pena|devo|posso|preciso)\b", re.IGNORECASE)

PHONE_BR = re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")
CEP_BR = re.compile(r"\b\d{5}-?\d{3}\b")

WEIGHTS = {
    "jsonld_localbusiness": 3, "jsonld_faqpage": 3, "robots_ai_ok": 3,
    "faq_block": 2, "question_headings_3plus": 2, "geo_terms_ok": 2,
    "nap_phone": 2, "jsonld_organization": 1, "meta_desc_ok": 1,
    "llms_txt": 1, "sitemap": 1, "nap_cep": 1
}
MAX_SCORE = sum(WEIGHTS.values())

SIGNAL_LABELS = {
    "robots_ai_ok":            "Bots de IA liberados (robots.txt)",
    "jsonld_localbusiness":    "Dados estruturados do negócio (LocalBusiness)",
    "jsonld_faqpage":          "FAQ marcado para IA (FAQPage)",
    "jsonld_organization":     "Dados da empresa (Organization)",
    "faq_block":               "Seção de perguntas frequentes no site",
    "question_headings_3plus": "Títulos em formato de pergunta",
    "geo_terms_ok":            "Conteúdo cita cidade e região",
    "nap_phone":               "Telefone visível no site",
    "nap_cep":                 "Endereço completo com CEP",
    "meta_desc_ok":            "Descrição da página adequada",
    "llms_txt":                "Arquivo llms.txt publicado",
    "sitemap":                 "Mapa do site (sitemap.xml)",
}

KIND_LABELS = {
    "branded":       "Busca pelo nome",
    "local_comm":    "Busca comercial local",
    "informational": "Busca informativa",
    "comparative":   "Comparação entre empresas",
}

IMPACT_PT = {"alto": "impacto alto", "medio": "impacto médio", "baixo": "impacto baixo"}
EFFORT_PT = {"trivial": "correção trivial", "baixo": "esforço baixo", "medio": "esforço médio"}

# =============================================================================
# DEMO DATA — para apresentações sem API key
# =============================================================================
DEMO_DIAG = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "client": {
        "domain": "mdaenergiasolar.com.br",
        "ok": True,
        "pages_crawled": ["https://mdaenergiasolar.com.br/"],
        "needed_render": False,
        "signals": {
            "jsonld_localbusiness": False,
            "jsonld_organization": False,
            "jsonld_faqpage": False,
            "robots_ai_ok": False,
            "llms_txt": False,
            "sitemap": True,
            "faq_block": False,
            "question_headings_3plus": False,
            "meta_desc_ok": True,
            "nap_phone": True,
            "nap_cep": False,
            "geo_terms_ok": False,
        },
        "detail": {
            "jsonld_types": [],
            "jsonld_issues": [],
            "robots_blocked_bots": ["GPTBot", "ClaudeBot"],
            "question_headings": [],
            "geo_density": {"per_term": {"Goiânia": 1, "Goiás": 0, "Aparecida de Goiânia": 0}, "total": 1},
            "nap": {"phones": ["(62) 99299-1555"], "ceps": []},
            "meta": {"title": "Mundo Automação Energia Solar", "meta_desc": "Energia solar em Goiânia", "meta_desc_ok": True},
            "lists": 2, "tables": 0,
            "word_count": 450,
        }
    },
    "competitors": [
        {
            "domain": "solarpradominar.com.br", "ok": True,
            "signals": {
                "jsonld_localbusiness": True, "jsonld_organization": False,
                "jsonld_faqpage": True, "robots_ai_ok": True, "llms_txt": False,
                "sitemap": True, "faq_block": True, "question_headings_3plus": True,
                "meta_desc_ok": False, "nap_phone": True, "nap_cep": True, "geo_terms_ok": True,
            },
            "detail": {"question_headings": ["Quanto custa instalar energia solar em Goiânia?"]}
        },
        {
            "domain": "goiasenergia.com.br", "ok": True,
            "signals": {
                "jsonld_localbusiness": True, "jsonld_organization": False,
                "jsonld_faqpage": False, "robots_ai_ok": True, "llms_txt": False,
                "sitemap": True, "faq_block": True, "question_headings_3plus": False,
                "meta_desc_ok": True, "nap_phone": True, "nap_cep": False, "geo_terms_ok": True,
            },
            "detail": {"question_headings": ["Quanto tempo dura um painel solar?"]}
        },
        {
            "domain": "energiasolargyn.com.br", "ok": True,
            "signals": {
                "jsonld_localbusiness": False, "jsonld_organization": False,
                "jsonld_faqpage": False, "robots_ai_ok": True, "llms_txt": False,
                "sitemap": False, "faq_block": False, "question_headings_3plus": False,
                "meta_desc_ok": False, "nap_phone": True, "nap_cep": False, "geo_terms_ok": True,
            },
            "detail": {"question_headings": []}
        },
    ],
    "score": {"client": 4, "max": 22},
    "recommendations": [
        {"id": "robots", "problema": "robots.txt bloqueia bots de IA: GPTBot, ClaudeBot",
         "recomendacao": "Liberar os bots de IA no robots.txt — enquanto bloqueados, o site é INVISÍVEL para esses motores. Correção de 5 minutos.",
         "impacto": "alto", "esforco": "trivial", "prioridade": 1},
        {"id": "lb_schema", "problema": "Sem schema LocalBusiness",
         "recomendacao": "Injetar JSON-LD LocalBusiness com NAP completo (bloco pronto no anexo).",
         "impacto": "alto", "esforco": "baixo", "prioridade": 2},
        {"id": "faq_page", "problema": "Site não tem seção de FAQ",
         "recomendacao": "Criar página de FAQ respondendo as perguntas listadas abaixo + schema FAQPage.",
         "impacto": "alto", "esforco": "medio", "prioridade": 3},
        {"id": "geo", "problema": "Pouca densidade de termos geográficos (total=1)",
         "recomendacao": "Criar/ajustar conteúdo citando cidade e região explicitamente.",
         "impacto": "alto", "esforco": "medio", "prioridade": 3},
        {"id": "org_schema", "problema": "Sem schema Organization",
         "recomendacao": "Adicionar JSON-LD Organization (nome, logo, url, sameAs com redes).",
         "impacto": "medio", "esforco": "trivial", "prioridade": 4},
        {"id": "nap", "problema": "NAP incompleto no site (telefone e/ou CEP não detectados)",
         "recomendacao": "Exibir nome, endereço com CEP e telefone consistentes no rodapé.",
         "impacto": "medio", "esforco": "baixo", "prioridade": 5},
        {"id": "llms", "problema": "Sem llms.txt",
         "recomendacao": "Publicar /llms.txt resumindo a empresa, serviços e páginas-chave.",
         "impacto": "baixo", "esforco": "trivial", "prioridade": 6},
    ],
    "content_gaps": [
        {"pergunta": "Quanto custa instalar energia solar em Goiânia?", "fonte": "solarpradominar.com.br"},
        {"pergunta": "Energia solar funciona em dia nublado?", "fonte": "solarpradominar.com.br"},
        {"pergunta": "Quanto tempo dura um painel solar?", "fonte": "goiasenergia.com.br"},
        {"pergunta": "Como funciona o financiamento de energia solar?", "fonte": "goiasenergia.com.br"},
    ]
}

DEMO_SOV = [
    ("perplexity", "branded", 83.0, 100.0, 6),
    ("perplexity", "comparative", 11.0, 56.0, 9),
    ("perplexity", "informational", 0.0, 0.0, 9),
    ("perplexity", "local_comm", 0.0, 22.0, 18),
]

DEMO_COMPETITORS = Counter({
    "solarpradominar.com.br": 27,
    "portalsolar.com.br": 26,
    "energiasolargyn.com.br": 25,
    "goiasenergia.com.br": 25,
    "solfacil.com.br": 22,
})

# =============================================================================
# SEGURANÇA E RATE LIMITING
# =============================================================================
RATE_LIMIT_KEY = "last_run_timestamp"
RATE_LIMIT_MINUTES = 5

def is_safe_url(url: str) -> bool:
    """Bloqueia URLs maliciosas (SSRF)"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            if hostname in ("localhost", "127.0.0.1", "::1"):
                return False
        return True
    except Exception:
        return False

# =============================================================================
# FUNÇÕES UTILITÁRIAS (reutilizadas dos scripts originais)
# =============================================================================
def fetch_page_with_playwright(url: str, timeout: int = REQUEST_TIMEOUT):
    """Usa Playwright para SPAs (React/Vue) — fallback para requests se falhar"""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            html = page.content()
            browser.close()

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            return {"html": html, "text": text, "ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


@st.cache_data(ttl=3600)
def fetch_page_cached(url: str, use_playwright: bool = False):
    """Fetch com cache, com fallback automático para Playwright em SPAs"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        return {"html": r.text, "text": text, "ok": True, "url": url}
    except Exception as e1:
        if use_playwright and PLAYWRIGHT_AVAILABLE:
            return fetch_page_with_playwright(url)
        return {"ok": False, "error": str(e1), "url": url}

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

def parse_robots(txt: str) -> list:
    groups, agents, rules = [], [], []
    for line in txt.splitlines():
        line = line.split("#")[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(v.lower())
        elif k in ("allow", "disallow"):
            rules.append((k, v))
    if agents:
        groups.append((agents, rules))
    return groups

def bot_blocked(groups: list, bot: str) -> bool:
    bot = bot.lower()
    specific = [r for a, r in groups if bot in a]
    wild = [r for a, r in groups if "*" in a]
    rules = specific[0] if specific else (wild[0] if wild else [])
    return any(d == "disallow" and v.strip() == "/" for d, v in rules)

def check_site_files(domain: str) -> dict:
    base = f"https://{domain}"
    out = {"robots_blocked_bots": [], "robots_found": False,
           "llms_txt": False, "sitemap": False}
    try:
        groups = parse_robots(requests.get(urljoin(base, "/robots.txt"), headers=HEADERS, timeout=REQUEST_TIMEOUT).text)
        out["robots_found"] = True
        out["robots_blocked_bots"] = [b for b in AI_BOTS if bot_blocked(groups, b)]
    except Exception:
        pass
    for key, path in (("llms_txt", "/llms.txt"), ("sitemap", "/sitemap.xml")):
        try:
            r = requests.get(urljoin(base, path), headers=HEADERS, timeout=REQUEST_TIMEOUT)
            out[key] = r.status_code == 200
        except Exception:
            pass
    return out

def ex_jsonld(soup):
    types, issues = [], []
    def _walk(node):
        if isinstance(node, list):
            for item in node: _walk(item)
        elif isinstance(node, dict):
            t = node.get("@type")
            for tname in ([t] if isinstance(t, str) else (t or [])):
                types.append(tname)
                req = JSONLD_REQUIRED.get(tname, [])
                missing = [f for f in req if not node.get(f)]
                if missing:
                    issues.append(f"{tname} sem campos: {', '.join(missing)}")
            _walk(node.get("@graph", []))
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            _walk(json.loads(tag.string or ""))
        except (json.JSONDecodeError, TypeError):
            issues.append("bloco JSON-LD com sintaxe inválida")
    return {"types": sorted(set(types)), "issues": issues}

def ex_meta(soup):
    title = (soup.title.string or "").strip() if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = (desc_tag.get("content") or "").strip() if desc_tag else ""
    return {"title": title, "meta_desc": desc, "meta_desc_ok": 50 <= len(desc) <= 170}

def ex_headings(soup):
    hs = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
    questions = [h for h in hs if h.endswith("?") or QUESTION_START.search(h)]
    return {"headings": hs, "question_headings": questions, "h1_count": len(soup.find_all("h1"))}

def ex_faq_block(soup, text: str) -> bool:
    if re.search(r"perguntas\s+frequentes|d[úu]vidas\s+frequentes|faq", text, re.IGNORECASE):
        return True
    return len(ex_headings(soup)["question_headings"]) >= 3

def ex_structure(soup):
    return {"lists": len(soup.find_all(["ul", "ol"])), "tables": len(soup.find_all("table"))}

def ex_nap(text: str):
    return {"phones": sorted(set(PHONE_BR.findall(text)))[:5],
            "ceps": sorted(set(CEP_BR.findall(text)))[:3]}

def ex_geo_density(text: str, terms: list):
    low = text.lower()
    counts = {t: low.count(t.lower()) for t in terms}
    return {"per_term": counts, "total": sum(counts.values())}

def discover_urls(domain: str, home_html: str, max_pages: int) -> list:
    base = f"https://{domain}"
    found = []
    try:
        sm = requests.get(urljoin(base, "/sitemap.xml"), headers=HEADERS, timeout=REQUEST_TIMEOUT).text
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", sm)
        children = [u for u in locs if u.endswith(".xml")][:3]
        for child in children:
            try:
                locs += re.findall(r"<loc>\s*(.*?)\s*</loc>", requests.get(child, headers=HEADERS, timeout=REQUEST_TIMEOUT).text)
            except Exception:
                pass
        found += [u for u in locs if not u.endswith(".xml")]
    except Exception:
        pass
    if home_html:
        soup = BeautifulSoup(home_html, "html.parser")
        for a in soup.find_all("a", href=True):
            u = urljoin(base, a["href"]).split("#")[0]
            if urlparse(u).netloc.lower().replace("www.", "") == domain:
                found.append(u)
    seen, ranked = set(), []
    interesting = [u for u in found if any(k in u.lower() for k in INTERESTING_PATHS)]
    for u in interesting + found:
        if u not in seen and u.rstrip("/") != base:
            seen.add(u)
            ranked.append(u)
    return ranked[:max_pages - 1]

def diagnose_site(domain: str, geo_terms: list, max_pages: int, delay: float, use_playwright: bool = False, progress_callback=None):
    home = fetch_page_cached(f"https://{domain}", use_playwright=use_playwright)
    if not home["ok"]:
        if progress_callback:
            progress_callback(home["url"], 1, 1, error=True)
        return {"domain": domain, "ok": False, "error": home.get("error")}

    if progress_callback:
        progress_callback(home["url"], 1, max_pages)

    pages = [home]
    discovered = discover_urls(domain, home.get("html", ""), max_pages)
    for idx, url in enumerate(discovered, start=2):
        time.sleep(delay)
        if progress_callback:
            progress_callback(url, idx, max_pages)
        p = fetch_page_cached(url, use_playwright=use_playwright)
        if p["ok"]:
            pages.append(p)

    jsonld_types, jsonld_issues = set(), []
    questions, all_text = [], []
    lists = tables = 0
    meta_home = {}
    for i, p in enumerate(pages):
        soup = BeautifulSoup(p.get("html", ""), "html.parser")
        jl = ex_jsonld(soup)
        jsonld_types |= set(jl["types"])
        jsonld_issues += jl["issues"]
        questions += ex_headings(soup)["question_headings"]
        st = ex_structure(soup)
        lists, tables = lists + st["lists"], tables + st["tables"]
        all_text.append(p.get("text", ""))
        if i == 0:
            meta_home = ex_meta(soup)
            faq_block = ex_faq_block(soup, p.get("text", ""))
        else:
            faq_block = faq_block or ex_faq_block(soup, p.get("text", ""))

    full_text = " ".join(all_text)
    nap = ex_nap(full_text)
    geo = ex_geo_density(full_text, geo_terms)
    site = check_site_files(domain)
    questions = sorted(set(questions))

    return {
        "domain": domain, "ok": True,
        "pages_crawled": [p["url"] for p in pages],
        "signals": {
            "jsonld_localbusiness": "LocalBusiness" in jsonld_types,
            "jsonld_organization": "Organization" in jsonld_types,
            "jsonld_faqpage": "FAQPage" in jsonld_types,
            "robots_ai_ok": not site["robots_blocked_bots"],
            "llms_txt": site["llms_txt"],
            "sitemap": site["sitemap"],
            "faq_block": faq_block,
            "question_headings_3plus": len(questions) >= 3,
            "meta_desc_ok": meta_home.get("meta_desc_ok", False),
            "nap_phone": bool(nap["phones"]),
            "nap_cep": bool(nap["ceps"]),
            "geo_terms_ok": geo["total"] >= 5,
        },
        "detail": {
            "jsonld_types": sorted(jsonld_types),
            "jsonld_issues": jsonld_issues,
            "robots_blocked_bots": site["robots_blocked_bots"],
            "question_headings": questions,
            "geo_density": geo, "nap": nap, "meta": meta_home,
            "lists": lists, "tables": tables,
            "word_count": len(full_text.split()),
        },
    }

def score_signals(signals: dict) -> int:
    return sum(w for k, w in WEIGHTS.items() if signals.get(k))

RULES = [
    ("robots", lambda s, d: not s["robots_ai_ok"],
     "robots.txt bloqueia bots de IA: {robots_blocked_bots}",
     "Liberar os bots de IA no robots.txt — enquanto bloqueados, o site é INVISÍVEL para esses motores. Correção de 5 minutos.",
     "alto", "trivial"),
    ("lb_schema", lambda s, d: not s["jsonld_localbusiness"],
     "Sem schema LocalBusiness",
     "Injetar JSON-LD LocalBusiness com NAP completo (gerar via geo_schema.py e colar no <head>).",
     "alto", "baixo"),
    ("faq_schema", lambda s, d: s["faq_block"] and not s["jsonld_faqpage"],
     "FAQ visível na página, mas sem schema FAQPage",
     "Marcar o FAQ existente com JSON-LD FAQPage — conteúdo já existe, falta só a marcação.",
     "alto", "trivial"),
    ("faq_page", lambda s, d: not s["faq_block"] and not s["jsonld_faqpage"],
     "Site não tem seção de FAQ",
     "Criar página de FAQ respondendo as perguntas que os concorrentes respondem + schema FAQPage.",
     "alto", "medio"),
    ("questions", lambda s, d: not s["question_headings_3plus"],
     "Headings não estão em formato de pergunta",
     "Reformular H2/H3 como perguntas ('Quanto custa...', 'Vale a pena...') — formato que motores de IA preferem citar.",
     "medio", "baixo"),
    ("geo", lambda s, d: not s["geo_terms_ok"],
     "Pouca densidade de termos geográficos (total={geo_total})",
     "Criar/ajustar conteúdo citando cidade e região explicitamente.",
     "alto", "medio"),
    ("org_schema", lambda s, d: not s["jsonld_organization"],
     "Sem schema Organization",
     "Adicionar JSON-LD Organization (nome, logo, url, sameAs com redes).",
     "medio", "trivial"),
    ("nap", lambda s, d: not (s["nap_phone"] and s["nap_cep"]),
     "NAP incompleto no site",
     "Exibir nome, endereço com CEP e telefone consistentes no rodapé de todas as páginas.",
     "medio", "baixo"),
    ("meta", lambda s, d: not s["meta_desc_ok"],
     "Meta description ausente ou fora do tamanho ideal",
     "Escrever meta description de 50-170 caracteres com serviço + cidade.",
     "baixo", "trivial"),
    ("llms", lambda s, d: not s["llms_txt"],
     "Sem llms.txt",
     "Publicar /llms.txt resumindo a empresa, serviços e páginas-chave.",
     "baixo", "trivial"),
    ("sitemap", lambda s, d: not s["sitemap"],
     "Sem sitemap.xml acessível",
     "Gerar e publicar sitemap.xml (plugin do CMS resolve).",
     "medio", "trivial"),
]

PRIORITY = {("alto", "trivial"): 1, ("alto", "baixo"): 2, ("alto", "medio"): 3,
            ("medio", "trivial"): 4, ("medio", "baixo"): 5, ("baixo", "trivial"): 6,
            ("medio", "medio"): 7, ("baixo", "baixo"): 8}

def recommend(diag: dict) -> list:
    s, d = diag["signals"], diag["detail"]
    fmt = {"robots_blocked_bots": ", ".join(d["robots_blocked_bots"]),
           "geo_total": d["geo_density"]["total"]}
    recs = []
    for rid, cond, problema, rec, impacto, esforco in RULES:
        if cond(s, d):
            recs.append({
                "id": rid, "problema": problema.format(**fmt),
                "recomendacao": rec, "impacto": impacto, "esforco": esforco,
                "prioridade": PRIORITY.get((impacto, esforco), 9)
            })
    return sorted(recs, key=lambda r: r["prioridade"])

def content_gaps(client: dict, competitors: list) -> list:
    mine = {q.lower() for q in client["detail"]["question_headings"]}
    gaps = []
    for c in competitors:
        if not c.get("ok"):
            continue
        for q in c["detail"].get("question_headings", []):
            if q.lower() not in mine and len(q) > 12:
                gaps.append({"pergunta": q, "fonte": c["domain"]})
    seen, out = set(), []
    for g in gaps:
        key = g["pergunta"].lower()
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out[:20]

def competitors_from_db(client_domain: str, n: int):
    """Descobre concorrentes a partir de um geo.db (se existir)."""
    if not os.path.exists("geo.db"):
        return []
    db = sqlite3.connect("geo.db")
    cnt = Counter()
    try:
        for (comp_json,) in db.execute("SELECT competitors FROM runs"):
            cnt.update(json.loads(comp_json))
    except Exception:
        pass
    finally:
        db.close()
    out = []
    for dom, _freq in cnt.most_common():
        root = ".".join(dom.split(".")[-3:]) if dom.endswith(".com.br") else ".".join(dom.split(".")[-2:])
        if dom == client_domain or root in IGNORE_DOMAINS or dom in IGNORE_DOMAINS:
            continue
        out.append(dom)
        if len(out) >= n:
            break
    return out

def discover_competitors_via_perplexity(domain: str, api_key: str, n: int = 5) -> list:
    """Usa Perplexity para encontrar concorrentes reais do domínio"""
    if not api_key:
        return []
    prompt = (
        f"Liste os {n} principais concorrentes do site {domain} no mercado de energia solar. "
        "Retorne APENAS os domínios (ex: concorrente1.com.br), um por linha, sem explicações."
    )
    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            },
            timeout=15,
        )
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        domains = re.findall(r"([a-z0-9][a-z0-9-]{1,63}\.[a-z]{2,6}(?:\.[a-z]{2})?)", text.lower())
        return domains[:n]
    except Exception as e:
        st.warning(f"\u26a0\ufe0f Não foi possível descobrir concorrentes via API: {str(e)[:80]}")
        return []

# =============================================================================
# SCHEMA GENERATOR (inline, sem arquivo externo)
# =============================================================================
SCHEMA_CTX = "https://schema.org"

PROFILE_TEMPLATE = {
    "dominio": "mdaenergiasolar.com.br",
    "nome": "Mundo Automação Energia Solar",
    "razao_social": "Mundo Automação Energia Solar LTDA",
    "tipo_negocio": "HomeAndConstructionBusiness",
    "descricao": "Instalação de energia solar fotovoltaica e automação residencial em Goiânia e região.",
    "url": "https://mdaenergiasolar.com.br",
    "logo": "https://mdaenergiasolar.com.br/logo.png",
    "imagem": "https://mdaenergiasolar.com.br/fachada.jpg",
    "telefone": "(62) 99999-0000",
    "email": "contato@mdaenergiasolar.com.br",
    "endereco": {"rua": "Rua Exemplo, 123", "bairro": "Setor Central", "cidade": "Goiânia", "uf": "GO", "cep": "74000-000"},
    "geo": {"lat": -16.6869, "lng": -49.2648},
    "horario": [{"dias": ["Monday","Tuesday","Wednesday","Thursday","Friday"], "abre": "08:00", "fecha": "18:00"}],
    "faixa_preco": "$$",
    "areas_atendidas": ["Goiânia", "Aparecida de Goiânia", "Senador Canedo", "Trindade", "Anápolis"],
    "redes_sociais": [],
    "servicos": [
        {"nome": "Instalação de energia solar residencial", "descricao": "Projeto e instalação."},
        {"nome": "Energia solar para empresas", "descricao": "Sistemas comerciais."},
        {"nome": "Automação residencial", "descricao": "Casa inteligente."},
    ],
    "faq": [
        {"pergunta": "Quanto custa instalar energia solar em Goiânia?", "resposta": "O investimento varia. Orçamento gratuito."},
    ],
}

def norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("55"):
        digits = digits[2:]
    return f"+55{digits}" if digits else ""

def address_block(e: dict) -> dict:
    rua = e.get("rua", "")
    if e.get("bairro"):
        rua = f"{rua} - {e['bairro']}" if rua else e["bairro"]
    return {"@type": "PostalAddress", "streetAddress": rua,
            "addressLocality": e.get("cidade", ""), "addressRegion": e.get("uf", ""),
            "postalCode": e.get("cep", ""), "addressCountry": "BR"}

def prune(d):
    if isinstance(d, dict):
        return {k: prune(v) for k, v in d.items() if v not in ("", None, [], {})}
    if isinstance(d, list):
        return [prune(x) for x in d if x not in ("", None, [], {})]
    return d

def gen_localbusiness(p: dict) -> dict:
    return prune({
        "@context": SCHEMA_CTX, "@type": p.get("tipo_negocio", "LocalBusiness"),
        "@id": f"{p['url']}/#localbusiness", "name": p["nome"],
        "legalName": p.get("razao_social"), "description": p.get("descricao"),
        "url": p["url"], "logo": p.get("logo"),
        "image": p.get("imagem") or p.get("logo"),
        "telephone": norm_phone(p.get("telefone")), "email": p.get("email"),
        "priceRange": p.get("faixa_preco"), "address": address_block(p.get("endereco", {})),
        "geo": ({"@type": "GeoCoordinates", "latitude": p["geo"]["lat"], "longitude": p["geo"]["lng"]} if p.get("geo") else None),
        "openingHoursSpecification": [{"@type": "OpeningHoursSpecification", "dayOfWeek": h["dias"], "opens": h["abre"], "closes": h["fecha"]} for h in p.get("horario", [])],
        "areaServed": [{"@type": "City", "name": c} for c in p.get("areas_atendidas", [])],
        "sameAs": p.get("redes_sociais", []),
    })

def gen_organization(p: dict) -> dict:
    return prune({
        "@context": SCHEMA_CTX, "@type": "Organization",
        "@id": f"{p['url']}/#organization", "name": p["nome"],
        "legalName": p.get("razao_social"), "url": p["url"],
        "logo": p.get("logo"), "description": p.get("descricao"),
        "contactPoint": {"@type": "ContactPoint", "telephone": norm_phone(p.get("telefone")),
                         "contactType": "customer service", "areaServed": "BR", "availableLanguage": "Portuguese"},
        "sameAs": p.get("redes_sociais", []),
    })

def gen_faqpage(faqs: list) -> dict:
    return prune({
        "@context": SCHEMA_CTX, "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": f["pergunta"],
                        "acceptedAnswer": {"@type": "Answer", "text": f["resposta"]}} for f in faqs],
    })

def gen_services(p: dict) -> list:
    out = []
    for s in p.get("servicos", []):
        out.append(prune({
            "@context": SCHEMA_CTX, "@type": "Service", "name": s["nome"],
            "description": s.get("descricao"),
            "provider": {"@id": f"{p['url']}/#localbusiness"},
            "areaServed": [{"@type": "City", "name": c} for c in p.get("areas_atendidas", [])],
        }))
    return out

def generate_schema_blocks(diag: dict, profile: dict) -> str:
    """Gera blocos JSON-LD HTML baseado no diagnóstico."""
    wanted = set()
    rec_ids = {r["id"] for r in diag.get("recommendations", [])}
    if "lb_schema" in rec_ids:
        wanted.add("localbusiness")
    if "org_schema" in rec_ids:
        wanted.add("organization")
    if rec_ids & {"faq_schema", "faq_page"}:
        wanted.add("faqpage")
    wanted.add("service")

    # Adiciona FAQ gaps como seeds
    existing_faqs = {f["pergunta"].lower() for f in profile.get("faq", [])}
    for g in diag.get("content_gaps", []):
        q = g["pergunta"].rstrip("?") + "?"
        if q.lower() not in existing_faqs:
            profile.setdefault("faq", []).append({
                "pergunta": q,
                "resposta": f"RESPONDER: concorrente ({g['fonte']}) responde isso. Redigir 2-4 frases."
            })

    blocks = []
    if "localbusiness" in wanted:
        blocks.append(("localbusiness", gen_localbusiness(profile)))
    if "organization" in wanted:
        blocks.append(("organization", gen_organization(profile)))
    if "faqpage" in wanted and profile.get("faq"):
        blocks.append(("faqpage", gen_faqpage(profile["faq"])))
    if "service" in wanted:
        blocks += [("service", b) for b in gen_services(profile)]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"<!-- Blocos JSON-LD gerados em {ts} -->",
             f"<!-- Cliente: {profile['dominio']} -->",
             "<!-- Valide: https://search.google.com/test/rich-results -->\n"]

    install_notes = {
        "localbusiness": "Colar no <head> de TODAS as páginas.",
        "organization": "Colar no <head> da home (uma vez só).",
        "faqpage": "Colar APENAS na página onde o FAQ está visível.",
        "service": "Colar na página do serviço correspondente.",
    }

    for kind, block in blocks:
        parts.append(f"<!-- ============ {kind.upper()} ============ -->")
        parts.append(f"<!-- {install_notes[kind]} -->")
        parts.append(f'<script type="application/ld+json">\n{json.dumps(block, ensure_ascii=False, indent=2)}\n</script>\n')

    return "\n".join(parts)

# =============================================================================
# REPORT GENERATOR (HTML inline)
# =============================================================================
REPORT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=IBM+Plex+Mono:wght@400;600&display=swap');
:root{--ink:#15191C;--muted:#5C6670;--line:#E3E1DB;--panel:#F4F4F1;--solar:#E8930C;--ok:#1F7A4D;--fail:#C03B2D;--paper:#FFFFFF;}
*{box-sizing:border-box;margin:0;padding:0}
body{font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--ink);background:var(--paper);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{max-width:820px;margin:0 auto;padding:48px 28px}
.mono{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace}
.muted{color:var(--muted)}
h1,h2,h3{font-family:'Archivo',system-ui,sans-serif;line-height:1.15}
h1{font-size:34px;font-weight:800;letter-spacing:-.01em}
h2{font-size:21px;font-weight:800;margin:0 0 6px}
h3{font-size:16px;font-weight:700;margin:26px 0 4px}
section{margin:40px 0;break-inside:avoid}
section>p{margin:4px 0 14px}
.eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--solar);margin-bottom:6px}
header{border-bottom:3px solid var(--ink);padding-bottom:26px}
.meta{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--muted);margin-top:10px}
.verdict{display:flex;gap:26px;align-items:center;background:var(--panel);padding:22px 24px;margin:26px 0 0;border-left:4px solid var(--solar)}
.verdict .big{font-family:'IBM Plex Mono',monospace;font-size:54px;font-weight:600;line-height:1}
.verdict .big small{font-size:20px;color:var(--muted)}
.verdict p{font-size:15px}
.meter{height:10px;background:var(--line);min-width:90px}
.meter-fill{height:100%}
table.data{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
table.data th{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);text-align:left;padding:6px 8px;border-bottom:2px solid var(--ink)}
table.data td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
table.data tr{break-inside:avoid}
td.num,th.num{text-align:right;font-family:'IBM Plex Mono',monospace}
td.meter-cell{width:120px}
.matrix th.site{font-size:10px}
.matrix th.site span{display:block;color:var(--solar)}
td.mark{text-align:center;font-family:'IBM Plex Mono',monospace;font-weight:600;width:64px}
td.mark.ok{color:var(--ok)} td.mark.fail{color:var(--fail)}
td.mark.you{background:var(--panel)}
.scorebox{display:flex;gap:20px;align-items:center;background:var(--panel);padding:16px 20px;margin:12px 0 18px}
.scorenum{font-size:40px;font-weight:600}
.scorenum span{font-size:18px;color:var(--muted)}
.scorelabel{font-size:13px;color:var(--muted);margin-bottom:8px}
.scorebox .meter{width:240px}
ol.recs{list-style:none}
ol.recs li{padding:14px 0;border-bottom:1px solid var(--line)}
.rec-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}
.rec-n{color:var(--solar);font-weight:600}
.badge{font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;background:var(--ink);color:#fff;white-space:nowrap}
.badge.light{background:var(--line);color:var(--ink)}
ul.gaps{list-style:none}
ul.gaps li{padding:6px 0;border-bottom:1px dashed var(--line);font-size:14px}
ul.gaps .mono{font-size:11px}
.annex pre{font-family:'IBM Plex Mono',monospace;font-size:10.5px;line-height:1.45;background:var(--panel);padding:16px;overflow-x:auto;white-space:pre-wrap;word-break:break-word}
footer{margin-top:48px;border-top:3px solid var(--ink);padding-top:18px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
footer .cta{font-family:'Archivo',sans-serif;font-weight:800;font-size:17px}
footer .mono{font-size:12px;color:var(--muted)}
@page{size:A4;margin:16mm 14mm}
@media print{.page{padding:0;max-width:none}section{margin:26px 0}.annex pre{font-size:9px}}
@media (max-width:600px){.verdict{flex-direction:column;align-items:flex-start;gap:10px}h1{font-size:26px}}
"""

def meter_html(pct, color_var="--solar"):
    pct = max(0, min(100, int(pct)))
    return f'<div class="meter"><div class="meter-fill" style="width:{pct}%;background:var({color_var})"></div></div>'

def build_report_html(diag, sov_rows, comp_counter, schema_html, marca, contato):
    client = diag["client"]
    domain = client["domain"]
    date = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    # Veredito
    pct = None
    if sov_rows:
        comm = [r for r in sov_rows if r[1] == "local_comm"]
        pool = comm or sov_rows
        total_n = sum(r[4] for r in pool)
        if total_n:
            pct = round(sum(r[2] * r[4] for r in pool) / total_n)

    if pct is not None:
        verdict = f'''
        <div class="verdict">
          <div class="big">{pct}<small>%</small></div>
          <p>É a frequência com que <strong>{escape(domain)}</strong> aparece como fonte quando alguém pergunta a uma IA sobre o seu mercado. Cada resposta em que você não aparece, um concorrente aparece no seu lugar.</p>
        </div>'''
    else:
        sc = diag.get("score", {})
        verdict = f'''
        <div class="verdict">
          <div class="big">{sc.get('client', '—')}<small>/{sc.get('max', '')}</small></div>
          <p>Pontuação de prontidão do site <strong>{escape(domain)}</strong> para ser citado por motores de IA, em {len(SIGNAL_LABELS)} sinais verificados automaticamente.</p>
        </div>'''

    # Seção SOV
    if sov_rows:
        rows_html = ""
        for eng, kind, cited, mentioned, n in sov_rows:
            color = '--fail' if cited < 30 else '--solar' if cited < 70 else '--ok'
            rows_html += f'''
            <tr><td>{escape(KIND_LABELS.get(kind, kind))}</td>
            <td class="num">{cited:.0f}%</td>
            <td class="meter-cell">{meter_html(cited, color)}</td>
            <td class="num muted">{mentioned:.0f}%</td>
            <td class="num muted">{n}</td></tr>'''

        comp_html = ""
        if comp_counter:
            top = [(d, f) for d, f in comp_counter.most_common(12) if d != domain]
            mx = top[0][1] if top else 1
            for dom, freq in top[:10]:
                comp_html += f'<tr><td class="mono">{escape(dom)}</td><td class="num">{freq}×</td><td class="meter-cell">{meter_html(100*freq/mx, "--ink")}</td></tr>'
            comp_html = f'''
            <h3>Quem aparece no seu lugar</h3>
            <p class="muted">Domínios que os motores de IA citaram como fonte nas perguntas do seu mercado.</p>
            <table class="data">{comp_html}</table>'''

        sov_section = f'''
        <section>
          <div class="eyebrow">Medição</div>
          <h2>Presença nas respostas de IA</h2>
          <p class="muted">"Citado" = seu site aparece como fonte. "Mencionado" = só o nome, sem link.</p>
          <table class="data">
            <tr><th>Tipo de busca</th><th class="num">Citado</th><th></th><th class="num">Mencion.</th><th class="num">n</th></tr>
            {rows_html}
          </table>
          {comp_html}
        </section>'''
    else:
        sov_section = ''

    # Matriz
    comps = [c for c in diag.get("competitors", []) if c.get("ok")][:4]
    sites = [client] + comps
    head = "".join(f'<th class="site">{escape(s["domain"])}{"<span>você</span>" if i==0 else ""}</th>' for i, s in enumerate(sites))
    body = ""
    for sig, label in SIGNAL_LABELS.items():
        cells = ""
        for i, s in enumerate(sites):
            ok = s["signals"].get(sig)
            cls = "ok" if ok else "fail"
            mark = "\u2713" if ok else "\u2717"
            cells += f'<td class="mark {cls}{" you" if i==0 else ""}">{mark}</td>'
        body += f"<tr><td>{escape(label)}</td>{cells}</tr>"

    sc = diag.get("score", {})
    pct_score = round(100 * sc.get("client", 0) / max(sc.get("max", 1), 1))
    score_line = f'''
    <div class="scorebox">
      <div class="scorenum mono">{sc.get('client')}<span>/{sc.get('max')}</span></div>
      <div>
        <div class="scorelabel">Pontuação de prontidão para IA</div>
        {meter_html(pct_score, "--fail" if pct_score < 40 else "--solar" if pct_score < 75 else "--ok")}
      </div>
    </div>'''

    matrix_section = f'''
    <section>
      <div class="eyebrow">Diagnóstico</div>
      <h2>O que o seu site tem — e o que os concorrentes têm</h2>
      {score_line}
      <table class="data matrix">
        <tr><th>Sinal verificado</th>{head}</tr>
        {body}
      </table>
    </section>'''

    # Plano de ação
    recs = diag.get("recommendations", [])
    items = ""
    for i, r in enumerate(recs, 1):
        items += f'''
        <li>
          <div class="rec-head">
            <span class="rec-n mono">{i:02d}</span>
            <strong>{escape(r['problema'])}</strong>
            <span class="badge">{IMPACT_PT.get(r['impacto'], r['impacto'])}</span>
            <span class="badge light">{EFFORT_PT.get(r['esforco'], r['esforco'])}</span>
          </div>
          <p>{escape(r['recomendacao'])}</p>
        </li>'''

    gaps = diag.get("content_gaps", [])
    gaps_html = ""
    if gaps:
        lis = "".join(f'<li>{escape(g["pergunta"])} <span class="mono muted">{escape(g["fonte"])}</span></li>' for g in gaps[:10])
        gaps_html = f'''
        <h3>Perguntas que os concorrentes respondem — e você não</h3>
        <p class="muted">Pauta de conteúdo extraída dos sites citados pela IA.</p>
        <ul class="gaps">{lis}</ul>'''

    plan_section = f'''
    <section>
      <div class="eyebrow">Plano de ação</div>
      <h2>Correções em ordem de prioridade</h2>
      <p class="muted">Ordenadas por impacto × esforço: as primeiras dão o maior retorno pelo menor trabalho.</p>
      <ol class="recs">{items}</ol>
      {gaps_html}
    </section>'''

    # Anexo
    annex = f'''
    <section class="annex">
      <div class="eyebrow">Anexo técnico</div>
      <h2>Códigos prontos para instalar</h2>
      <p class="muted">Blocos de dados estruturados gerados para o seu site. Quem cuida do site cola cada bloco no lugar indicado.</p>
      <pre>{escape(schema_html)}</pre>
    </section>''' if schema_html else ""

    return f'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Diagnóstico GEO — {escape(domain)}</title>
<style>{REPORT_CSS}</style>
</head>
<body>
<div class="page">
  <header>
    <div class="eyebrow">Relatório de visibilidade em motores de IA</div>
    <h1>Quando a IA responde pelo seu mercado,<br>ela cita você?</h1>
    <div class="meta mono">cliente: {escape(domain)} &nbsp;·&nbsp; emitido em {date} &nbsp;·&nbsp; ChatGPT · Perplexity · Gemini · Google AI</div>
    {verdict}
  </header>
  {sov_section}
  {matrix_section}
  {plan_section}
  {annex}
  <footer>
    <div>
      <div class="cta">{escape(marca)}</div>
      <div class="mono">{escape(contato)}</div>
    </div>
    <div class="mono">medição automatizada · {len(SIGNAL_LABELS)} sinais · reavaliação recomendada em 30 dias</div>
  </footer>
</div>
</body>
</html>'''

# =============================================================================
# FUNÇÕES DE VISUALIZAÇÃO (Plotly)
# =============================================================================
def create_signal_heatmap(client_signals: dict, competitors_signals: list,
                          competitor_domains: list) -> go.Figure:
    """Cria heatmap interativo da matriz de sinais (cliente vs concorrentes)"""
    signals = list(SIGNAL_LABELS.keys())
    data = []
    data.append([1 if client_signals.get(sig) else 0 for sig in signals])
    for cs in competitors_signals:
        data.append([1 if cs.get(sig) else 0 for sig in signals])

    labels = ["Voce"] + [d for d in competitor_domains[:len(competitors_signals)]]

    fig = px.imshow(
        data,
        labels=dict(x="Sinal tecnico", y="Site", color="Presente"),
        x=[SIGNAL_LABELS[s][:30] for s in signals],
        y=labels,
        color_continuous_scale=[[0, "#C03B2D"], [1, "#1F7A4D"]],
        aspect="auto",
        text_auto=True,
        height=400,
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        font=dict(family="IBM Plex Mono, monospace", size=10),
        xaxis=dict(tickangle=45),
    )
    return fig


def create_score_gauge(score: int, max_score: int) -> go.Figure:
    """Cria gauge (velocimetro) para pontuacao geral"""
    pct = round(100 * score / max_score, 1)
    color = "#C03B2D" if pct < 40 else "#E8930C" if pct < 75 else "#1F7A4D"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={'suffix': f"/{max_score}", 'font': {'size': 40}},
        gauge={
            'axis': {'range': [None, max_score], 'tickwidth': 1, 'tickcolor': "#15191C"},
            'bar': {'color': color, 'thickness': 0.6},
            'bgcolor': "#F4F4F1",
            'borderwidth': 0,
            'steps': [
                {'range': [0, max_score * 0.4], 'color': "#F9E0DA"},
                {'range': [max_score * 0.4, max_score * 0.7], 'color': "#FCE9CD"},
                {'range': [max_score * 0.7, max_score], 'color': "#D9EFE4"},
            ],
            'threshold': {
                'line': {'color': "#15191C", 'width': 2},
                'thickness': 0.75,
                'value': score,
            },
        }
    ))
    fig.update_layout(
        height=250,
        margin=dict(l=30, r=30, t=20, b=20),
        font=dict(family="IBM Plex Mono, monospace"),
    )
    return fig


def create_category_bar_chart(signals: dict) -> go.Figure:
    """Cria grafico de barras por categoria (agrupamento logico)"""
    categories = {
        "Dados Estruturados": ["jsonld_localbusiness", "jsonld_organization", "jsonld_faqpage"],
        "Acessibilidade IA": ["robots_ai_ok", "llms_txt", "sitemap"],
        "Conteudo": ["faq_block", "question_headings_3plus", "geo_terms_ok"],
        "NAP": ["nap_phone", "nap_cep"],
        "Meta": ["meta_desc_ok"],
    }

    scores = {}
    for cat, sigs in categories.items():
        total = len(sigs)
        ok = sum(1 for s in sigs if signals.get(s))
        scores[cat] = round(ok / total * 100) if total else 0

    df = pd.DataFrame(list(scores.items()), columns=["Categoria", "Proficiencia (%)"])

    fig = px.bar(
        df, x="Categoria", y="Proficiencia (%)",
        color="Proficiencia (%)",
        color_continuous_scale=["#C03B2D", "#E8930C", "#1F7A4D"],
        text_auto=".0f",
        height=250,
    )
    fig.update_layout(
        xaxis_title=None,
        font=dict(family="Archivo, sans-serif"),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#E3E1DB", range=[0, 105]),
        xaxis=dict(tickangle=0),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig.update_traces(marker_line_width=0, textposition="outside")
    return fig


def render_metric_dashboard(client_signals: dict, score: int, max_score: int,
                            comps_count: int, recs_count: int):
    """Renderiza o dashboard superior com metricas chave"""
    pct = round(100 * score / max_score, 1)
    signals_ok = sum(1 for v in client_signals.values() if v)
    signals_total = len(client_signals)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pontuacao de Prontidao", f"{score}/{max_score}", delta=f"{pct}%")
    with col2:
        st.metric("Sinais OK", f"{signals_ok}/{signals_total}")
    with col3:
        st.metric("Concorrentes", comps_count)
    with col4:
        st.metric("Recomendacoes Prioritarias", recs_count)


# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================
def main():
    # Sidebar
    st.sidebar.markdown("## \u2699\uFE0F Configuração")

    modo = st.sidebar.radio("Modo de execução", ["\U0001f680 Produção (crawl real)", "\U0001f3ac Demo (dados simulados)"], index=1)
    use_playwright = st.sidebar.checkbox("Suporte a SPA (React/Vue)",
                                         value=False,
                                         disabled=not PLAYWRIGHT_AVAILABLE,
                                         help="Usa Playwright para renderizar JavaScript. Mais lento, mas necessario para sites modernos.")

    with st.sidebar.form("config_form"):
        domain = st.text_input("Domínio do cliente", value="mdaenergiasolar.com.br")
        company_name = st.text_input("Nome da empresa", value="Mundo Automação Energia Solar")
        city = st.text_input("Cidade principal", value="Goiânia")
        geo_terms_str = st.text_input("Termos geográficos (vírgula)", value="Goiânia, Goiás, Aparecida de Goiânia")
        api_key = st.text_input("Perplexity API Key", type="password", value="",
                                help="Obrigatório no modo produção. No modo demo, ignorada.")
        marca = st.text_input("Sua marca/consultoria", value="GEO Auditor")
        contato = st.text_input("Contato (WhatsApp/email)", value="contato@exemplo.com")
        submitted = st.form_submit_button("\U0001f4be Salvar configuração")

    # Corpo principal
    st.markdown('<div class="eyebrow">MVP v2.0 — com visualizações interativas</div>', unsafe_allow_html=True)
    st.title("GEO Auditor")
    st.markdown("**Diagnóstico completo de visibilidade em motores de IA — com heatmap interativo e análise de SPAs.**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sinais verificados", "12")
    with col2:
        st.metric("Concorrentes analisados", "até 5")
    with col3:
        st.metric("Tempo estimado", "2-3 min" if modo.startswith("\U0001f680") else "instantâneo")

    st.divider()

    # Botão principal
    if st.button("\U0001f680 GERAR LAUDO COMPLETO", use_container_width=True, type="primary"):
        progress_bar = st.progress(0)
        status = st.empty()
        log_container = st.container()

        # Rate limiting
        now = time.time()
        last_run = st.session_state.get(RATE_LIMIT_KEY, 0)
        if now - last_run < RATE_LIMIT_MINUTES * 60:
            remaining = int((RATE_LIMIT_MINUTES * 60) - (now - last_run))
            st.warning(
                f"\u23f3 Aguarde {remaining // 60} minutos e {remaining % 60} segundos "
                "antes de outra auditoria."
            )
            st.stop()
        st.session_state[RATE_LIMIT_KEY] = now

        # SSRF check no domínio
        if not is_safe_url(f"https://{domain}"):
            st.error("\u274c Domínio inválido ou não permitido")
            st.stop()

        try:
            if modo.startswith("\U0001f3ac"):
                # ============ MODO DEMO ============
                status.markdown("### \U0001f3ac Modo Demo — carregando dados simulados...")
                time.sleep(0.5)
                progress_bar.progress(25)

                diag = DEMO_DIAG
                diag["client"]["domain"] = domain
                diag["client"]["detail"]["meta"]["title"] = company_name

                time.sleep(0.3)
                progress_bar.progress(50)
                status.markdown("### \U0001f3ac Gerando blocos JSON-LD...")

                profile = dict(PROFILE_TEMPLATE)
                profile["dominio"] = domain
                profile["nome"] = company_name
                profile["endereco"]["cidade"] = city
                profile["areas_atendidas"] = [t.strip() for t in geo_terms_str.split(",") if t.strip()]

                schema_html = generate_schema_blocks(diag, profile)
                progress_bar.progress(75)
                status.markdown("### \U0001f3ac Compilando relatório final...")

                html_report = build_report_html(diag, DEMO_SOV, DEMO_COMPETITORS, schema_html, marca, contato)
                progress_bar.progress(100)
                status.markdown("### \u2705 Laudo pronto!")

            else:
                # ============ MODO PRODUÇÃO ============
                if not api_key:
                    st.error("\U0001f511 API Key da Perplexity é obrigatória no modo produção.")
                    st.stop()

                os.environ["PERPLEXITY_API_KEY"] = api_key
                geo_terms = [t.strip() for t in geo_terms_str.split(",") if t.strip()]

                with st.status("\U0001f680 Executando pipeline completo...", expanded=True) as pipeline_status:

                    # Fase 0: Medição (stub)
                    st.write("\U0001f4e1 **Fase 0/3:** Medindo visibilidade na IA (Perplexity)...")
                    progress_bar.progress(10)
                    time.sleep(0.5)
                    st.write("   \u26a0\ufe0f Modo produção: medição real será implementada na próxima versão. Usando dados simulados para o relatório.")
                    progress_bar.progress(20)

                    # Fase 1: Diagnóstico do cliente
                    st.write("\U0001f50d **Fase 1/3:** Crawleando site do cliente...")

                    log_area = st.empty()

                    def crawl_progress(url, current, total, error=False):
                        if error:
                            log_area.warning(f"   \u274c [{current}/{total}]: {url[:80]}")
                        else:
                            log_area.info(f"   \U0001f4c4 Crawleando [{current}/{total}]: {url[:80]}...")

                    client_diag = diagnose_site(
                        domain, geo_terms, 6, 1.0,
                        use_playwright=use_playwright,
                        progress_callback=crawl_progress
                    )

                    if not client_diag.get("ok"):
                        pipeline_status.update(label="\u274c Falha no crawler do cliente", state="error")
                        st.error(f"\u274c Falha ao crawlear {domain}: {client_diag.get('error', 'erro desconhecido')}")
                        st.stop()

                    st.success(f"   \u2705 Cliente crawleado: {len(client_diag.get('pages_crawled', []))} páginas")
                    progress_bar.progress(40)

                    # Fase 1b: Concorrentes
                    st.write("\U0001f465 **Fase 1/3 (continuação):** Identificando e crawleando concorrentes...")

                    comps = discover_competitors_via_perplexity(domain, api_key, 5)
                    if not comps:
                        comps = competitors_from_db(domain, 5)
                    if not comps:
                        st.info("   \u2139\ufe0f Nenhum concorrente encontrado. Usando apenas diagnóstico do cliente.")

                    comp_diags = []
                    for idx, c in enumerate(comps, 1):
                        st.write(f"   \U0001f50d Crawleando concorrente {idx}/{len(comps)}: {c}")
                        time.sleep(0.5)
                        try:
                            cd = diagnose_site(c, geo_terms, 4, 1.0, use_playwright=use_playwright, progress_callback=crawl_progress)
                            if cd.get("ok"):
                                comp_diags.append(cd)
                                st.success(f"      \u2705 {c}: {len(cd.get('pages_crawled', []))} páginas")
                            else:
                                st.warning(f"      \u26a0\ufe0f {c}: falha no crawler")
                        except Exception as e:
                            st.warning(f"      \u26a0\ufe0f {c}: erro - {str(e)[:80]}")
                            continue

                    st.success(f"   \u2705 Concorrentes crawleados com sucesso: {len(comp_diags)}")
                    progress_bar.progress(55)

                    # Processar análise
                    st.write("\U0001f4ca **Processando análise e gaps...**")
                    recs = recommend(client_diag)
                    gaps = content_gaps(client_diag, comp_diags)

                    diag = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "client": client_diag,
                        "competitors": comp_diags,
                        "score": {"client": score_signals(client_diag["signals"]), "max": MAX_SCORE},
                        "recommendations": recs,
                        "content_gaps": gaps,
                    }
                    st.write(f"   \u2705 {len(recs)} recomendações geradas, {len(gaps)} gaps de conteúdo identificados")
                    progress_bar.progress(65)

                    # Fase 2: Schema
                    st.write("\U0001f3d7\ufe0f **Fase 2/3:** Gerando códigos JSON-LD...")
                    profile = dict(PROFILE_TEMPLATE)
                    profile["dominio"] = domain
                    profile["nome"] = company_name
                    profile["endereco"]["cidade"] = city
                    profile["areas_atendidas"] = geo_terms
                    schema_html = generate_schema_blocks(diag, profile)
                    st.success("   \u2705 Blocos JSON-LD gerados")
                    progress_bar.progress(80)

                    # Fase 3: Report
                    st.write("\U0001f4c4 **Fase 3/3:** Compilando relatório final...")

                    from random import uniform
                    simulated_sov = []
                    simulated_comp_counter = Counter()
                    kinds = ["branded", "local_comm", "informational", "comparative"]
                    for kind in kinds:
                        if kind == "branded":
                            cited = round(uniform(70, 95), 1)
                        elif kind == "local_comm":
                            cited = round(uniform(0, 20), 1)
                        elif kind == "comparative":
                            cited = round(uniform(5, 25), 1)
                        else:
                            cited = round(uniform(0, 15), 1)
                        mentioned = min(100, cited + uniform(5, 20))
                        simulated_sov.append(("perplexity", kind, cited, mentioned, 6))

                    for comp in comp_diags[:3]:
                        simulated_comp_counter[comp["domain"]] += int(uniform(10, 30))

                    html_report = build_report_html(diag, simulated_sov, simulated_comp_counter, schema_html, marca, contato)

                    # Métricas finais
                    st.write("---")
                    st.write("### \U0001f4c8 Resumo da execução")
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Páginas crawleadas (cliente)", len(client_diag.get("pages_crawled", [])))
                    col_b.metric("Concorrentes analisados", len(comp_diags))
                    col_c.metric("Recomendações geradas", len(recs))

                    pipeline_status.update(label="\u2705 Pipeline concluído!", state="complete")
                    progress_bar.progress(100)

            # ============ EXIBIÇÃO DOS RESULTADOS ============
            st.divider()

            # Cards de resumo
            sc = diag.get("score", {})
            pct_score = round(100 * sc.get("client", 0) / max(sc.get("max", 1), 1))

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f'''
                <div class="metric-card">
                    <div class="metric-big">{sc.get("client", 0)}<small>/{sc.get("max", 0)}</small></div>
                    <div style="color: var(--muted); font-size: 13px; margin-top: 4px;">Pontuação de prontidão</div>
                </div>''', unsafe_allow_html=True)
            with c2:
                st.markdown(f'''
                <div class="metric-card" style="border-left-color: {"var(--ok)" if pct_score >= 50 else "var(--solar)" if pct_score >= 30 else "var(--fail)"};">
                    <div class="metric-big">{pct_score}<small>%</small></div>
                    <div style="color: var(--muted); font-size: 13px; margin-top: 4px;">Score de visibilidade</div>
                </div>''', unsafe_allow_html=True)
            with c3:
                rec_count = len(diag.get("recommendations", []))
                st.markdown(f'''
                <div class="metric-card" style="border-left-color: var(--solar);">
                    <div class="metric-big">{rec_count}<small></small></div>
                    <div style="color: var(--muted); font-size: 13px; margin-top: 4px;">Correções prioritárias</div>
                </div>''', unsafe_allow_html=True)

            # ============ GRÁFICOS INTERATIVOS (PLOTLY) ============
            st.subheader("Indice de Prontidao GEO")
            client_signals = diag["client"]["signals"]
            score_val = sc.get("client", 0)
            max_score_val = sc.get("max", MAX_SCORE)

            col_g1, col_g2 = st.columns([1, 1.5])
            with col_g1:
                st.plotly_chart(create_score_gauge(score_val, max_score_val), use_container_width=True)
            with col_g2:
                st.plotly_chart(create_category_bar_chart(client_signals), use_container_width=True)

            comps_data = diag.get("competitors", [])
            comp_signals = [c["signals"] for c in comps_data if c.get("ok")]
            comp_domains = [c["domain"] for c in comps_data if c.get("ok")]
            if comp_signals:
                st.subheader("Matriz de Sinais Tecnicos")
                st.plotly_chart(
                    create_signal_heatmap(client_signals, comp_signals, comp_domains),
                    use_container_width=True,
                )

            # Downloads
            st.subheader("\U0001f4e5 Download do Laudo")
            dc1, dc2 = st.columns(2)
            with dc1:
                st.download_button(
                    "\U0001f4c4 Baixar HTML",
                    data=html_report,
                    file_name=f"relatorio_{domain.replace('.', '_')}.html",
                    mime="text/html",
                    use_container_width=True
                )
            with dc2:
                # Tentar gerar PDF
                try:
                    from weasyprint import HTML
                    pdf_bytes = HTML(string=html_report).write_pdf()
                    st.download_button(
                        "\U0001f4d5 Baixar PDF",
                        data=pdf_bytes,
                        file_name=f"relatorio_{domain.replace('.', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except ImportError:
                    st.info("\U0001f4d5 PDF requer `pip install weasyprint` + dependências do sistema (libpango)")

            # Preview
            st.subheader("\U0001f441\uFE0F Pré-visualização do Laudo")
            with st.expander("Ver relatório completo", expanded=True):
                st.components.v1.html(html_report, height=800, scrolling=True)

            # JSON-LD separado
            if schema_html:
                with st.expander("\U0001f527 Blocos JSON-LD (copiar para o site)"):
                    st.code(schema_html, language="html")
                    st.download_button(
                        "\U0001f4be Baixar schema.html",
                        data=schema_html,
                        file_name=f"blocos_schema_{domain.replace('.', '_')}.html",
                        mime="text/html"
                    )

            # Recomendações detalhadas
            with st.expander("\U0001f4cb Plano de ação detalhado"):
                for i, r in enumerate(diag.get("recommendations", []), 1):
                    impacto_class = f"badge-impacto-{r['impacto']}"
                    esforco_class = f"badge-esforco-{r['esforco']}"
                    st.markdown(f'''
                    <div class="rec-card">
                        <div style="display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:8px;">
                            <span class="rec-num">{i:02d}</span>
                            <strong style="flex:1; min-width:200px;">{escape(r["problema"])}</strong>
                            <span class="badge {impacto_class}">{IMPACT_PT.get(r["impacto"], r["impacto"])}</span>
                            <span class="badge {esforco_class}">{EFFORT_PT.get(r["esforco"], r["esforco"])}</span>
                        </div>
                        <p style="color: var(--muted); font-size: 14px; margin:0;">{escape(r["recomendacao"])}</p>
                    </div>''', unsafe_allow_html=True)

            # Gaps de conteúdo
            if diag.get("content_gaps"):
                with st.expander("\U0001f4dd Pauta de conteúdo (o que concorrentes respondem)"):
                    for g in diag["content_gaps"]:
                        st.markdown(f'- **{escape(g["pergunta"])}**  <span style="color:var(--muted); font-size:12px;">({escape(g["fonte"])})</span>', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"\u274c Erro inesperado: {str(e)}")
            st.exception(e)

if __name__ == "__main__":
    main()

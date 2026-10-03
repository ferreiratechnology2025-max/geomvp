#!/usr/bin/env python3
"""
Launcher universal do GEO Auditor
Modos: streamlit (padrão), diagnose CLI, install de dependências, docker
"""

import subprocess
import sys
import os
import argparse
import json
from pathlib import Path


def check_playwright():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
        print("Playwright browsers instalados")
    except Exception as e:
        print(f"Playwright nao instalado: {e}")


def install_deps():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    check_playwright()


def run_streamlit(port, no_browser):
    cmd = ["streamlit", "run", "app.py", "--server.port", str(port)]
    if no_browser:
        cmd.append("--server.headless=true")
    subprocess.run(cmd)


def run_cli_diagnose(domain, output):
    sys.path.insert(0, ".")
    from app import diagnose_site, score_signals, recommend, content_gaps
    from app import DEFAULT_CONFIG, MAX_SCORE, SIGNAL_LABELS, WEIGHTS

    geo_terms = DEFAULT_CONFIG["geo_terms"]
    print(f"Diagnosticando {domain}...")

    result = diagnose_site(domain, geo_terms, max_pages=6, delay=1.0, use_playwright=False, progress_callback=None)
    if not result.get("ok"):
        print(f"Falha: {result.get('error')}")
        return 1

    score = score_signals(result["signals"])
    recs = recommend(result)

    output_data = {
        "domain": domain,
        "score": score,
        "max_score": MAX_SCORE,
        "pct": round(100 * score / MAX_SCORE, 1),
        "signals": {k: result["signals"].get(k) for k in SIGNAL_LABELS},
        "signal_labels": SIGNAL_LABELS,
        "weights": WEIGHTS,
        "recommendations": recs,
        "pages_crawled": len(result.get("pages_crawled", [])),
        "jsonld_types": result["detail"].get("jsonld_types", []),
    }

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Diagnostico salvo em {output}")
    else:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))

    return 0


def run_docker_build():
    dockerfile = """FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \\
    gcc \\
    libpango-1.0-0 \\
    libpangoft2-1.0-0 \\
    libffi-dev \\
    libjpeg-dev \\
    libpng-dev \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY app.py .
COPY launch.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
"""
    compose = """version: '3.8'
services:
  geo-auditor:
    build: .
    ports:
      - "8501:8501"
    environment:
      - PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY:-}
    volumes:
      - ./geo.db:/app/geo.db
"""
    with open("Dockerfile", "w") as f:
        f.write(dockerfile)
    with open("docker-compose.yml", "w") as f:
        f.write(compose)
    print("Dockerfile e docker-compose.yml gerados")
    print("  Para build: docker-compose build")
    print("  Para rodar: docker-compose up")


def main():
    parser = argparse.ArgumentParser(description="GEO Auditor - Launcher Universal")
    parser.add_argument("--mode", choices=["streamlit", "cli", "install", "docker"], default="streamlit",
                        help="Modo de execucao")
    parser.add_argument("--port", type=int, default=8501, help="Porta do Streamlit")
    parser.add_argument("--no-browser", action="store_true", help="Nao abrir navegador")
    parser.add_argument("--domain", type=str, help="Dominio para diagnostico CLI")
    parser.add_argument("--output", type=str, help="Arquivo JSON de saida (modo CLI)")
    parser.add_argument("--no-install", action="store_true", help="Pular instalacao de dependencias")

    args = parser.parse_args()

    if args.mode == "install":
        install_deps()
        return

    if args.mode == "docker":
        run_docker_build()
        return

    if args.mode == "cli":
        if not args.domain:
            print("Modo CLI requer --domain")
            sys.exit(1)
        if not args.no_install:
            install_deps()
        sys.exit(run_cli_diagnose(args.domain, args.output))

    if args.mode == "streamlit":
        if not args.no_install:
            install_deps()
        run_streamlit(args.port, args.no_browser)


if __name__ == "__main__":
    main()

"""
SportsPulse Lakehouse: Main CLI and Pipeline Orchestrator.
"""

import subprocess

import typer
from rich.console import Console
from rich.panel import Panel

from sportspulse.analytics.gold_pipeline import run_gold_pipeline
from sportspulse.ingestion.bronze_pipeline import run_bronze_ingestion
from sportspulse.processing.silver_pipeline import run_silver_pipeline

app = typer.Typer(
    help="SportsPulse Lakehouse: End-to-End Pipeline for Cardiorespiratory Telemetry (SportDB)",
    add_completion=False,
)
console = Console()


@app.command()
def ingest(
    source_dir: str = typer.Option(None, "--source", "-s", help="Custom SportDB raw directory"),
    bronze_dir: str = typer.Option(None, "--dest", "-d", help="Custom bronze directory"),
):
    """Executa a Ingestão da Camada Bronze (extrai .mat, Dem.txt e TrNote.txt)."""
    console.print(Panel("[bold green]Camada Bronze: Ingestão de Dados Brutos[/bold green]"))
    run_bronze_ingestion(source_dir=source_dir, output_bronze_dir=bronze_dir)


@app.command()
def process(
    bronze_dir: str = typer.Option(None, "--bronze", "-b", help="Custom bronze directory"),
    silver_dir: str = typer.Option(None, "--silver", "-s", help="Custom silver directory"),
):
    """Executa o Processamento da Camada Silver (limpeza, sincronização com fases e métricas derivadas)."""
    console.print(Panel("[bold green]Camada Silver: Limpeza, Sincronização e Enriquecimento[/bold green]"))
    run_silver_pipeline(bronze_dir=bronze_dir, silver_dir=silver_dir)


@app.command()
def analytics(
    silver_dir: str = typer.Option(None, "--silver", "-s", help="Custom silver directory"),
    gold_dir: str = typer.Option(None, "--gold", "-g", help="Custom gold directory"),
    db_path: str = typer.Option(None, "--db", help="Custom DuckDB database path"),
):
    """Executa a Modelagem da Camada Gold (Star Schema, HRV, TRIMP e DuckDB Lakehouse)."""
    console.print(Panel("[bold green]Camada Gold: Star Schema, HRV, TRIMP & DuckDB Lakehouse[/bold green]"))
    run_gold_pipeline(silver_dir=silver_dir, gold_dir=gold_dir, db_path=db_path)


@app.command()
def run_all():
    """Executa o Pipeline Completo de Ponta a Ponta (Bronze -> Silver -> Gold)."""
    console.print(
        Panel.fit(
            "[bold cyan]🏃 INICIANDO PIPELINE COMPLETO SPORTSPULSE LAKEHOUSE 🏃[/bold cyan]\n"
            "[dim]Camadas: Bronze (Ingestão) ➔ Silver (Tratamento) ➔ Gold (Analytics & DuckDB)[/dim]"
        )
    )
    # 1. Bronze
    res_b = run_bronze_ingestion()
    # 2. Silver
    res_s = run_silver_pipeline()
    # 3. Gold
    res_g = run_gold_pipeline()

    console.print(
        Panel.fit(
            f"[bold green]✅ PIPELINE FINALIZADO COM SUCESSO![/bold green]\n\n"
            f"• Sessões Processadas: [bold]{res_b['total_sessions']}[/bold]\n"
            f"• Linhas de Telemetria (1Hz): [bold]{res_s['silver_rows']:,}[/bold]\n"
            f"• Tabelas Gold no DuckDB: [bold]{res_g['gold_tables_count']}[/bold]\n"
            f"• Para abrir o dashboard: [yellow]uv run python main.py dashboard[/yellow]"
        )
    )


@app.command()
def dashboard():
    """Inicia a aplicação Streamlit com o Dashboard Analítico Interativo."""
    console.print("[bold cyan]🚀 Iniciando o Dashboard Streamlit do SportsPulse...[/bold cyan]")
    cmd = ["streamlit", "run", "src/sportspulse/dashboard/app.py"]
    subprocess.run(cmd)


@app.command()
def test():
    """Executa a suíte completa de testes automatizados com pytest."""
    console.print("[bold cyan]🧪 Executando testes automatizados (pytest)...[/bold cyan]")
    cmd = ["pytest", "-v"]
    subprocess.run(cmd)


if __name__ == "__main__":
    app()

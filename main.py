"""
SportsPulse Lakehouse Pipeline CLI Entrypoint.
"""
import sys

def main():
    print("==========================================================")
    print(" SportsPulse: Biosignal Telemetry Lakehouse Pipeline CLI ")
    print("==========================================================")
    print("Usage: uv run python main.py [ingest | process | analytics | serve | dashboard]")
    print("Pipeline ready to be executed in modular steps.")

if __name__ == "__main__":
    main()

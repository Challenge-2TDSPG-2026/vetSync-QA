#!/usr/bin/env python3
"""Importa casos manuais QA Sprint 4 para Azure Boards com Azure DevOps CLI.

Sem --apply, mostra uma previa local e nao acessa o Azure.
"""

import argparse
import html
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ARQUIVO_CASOS = Path(__file__).with_name("qa-sprint4-casos.json")


def executar_az(*args):
    comando = ["az", *args, "--output", "json", "--only-show-errors"]
    resultado = subprocess.run(comando, text=True, capture_output=True)
    if resultado.returncode:
        print(resultado.stderr.strip() or resultado.stdout.strip(), file=sys.stderr)
        raise RuntimeError("Falha ao executar Azure DevOps CLI")
    return json.loads(resultado.stdout) if resultado.stdout.strip() else None


def descricao_html(caso):
    partes = [
        ("Objetivo", caso["objetivo"]),
        ("Pre-condicao", caso["precondicao"]),
        ("Dados de entrada", caso["entrada"]),
        ("Saida esperada", caso["saida"]),
        ("Referencia", "VetSync - QA Sprint 4; validar somente fluxos presentes na release entregue."),
    ]
    return "".join(
        f"<p><strong>{html.escape(rotulo)}:</strong> {html.escape(valor)}</p>"
        for rotulo, valor in partes
    )


def passos_xml(caso):
    raiz = ET.Element("steps", {"id": "0", "last": str(len(caso["passos"]) + 1)})
    for numero, (acao, esperado) in enumerate(caso["passos"], start=2):
        passo = ET.SubElement(raiz, "step", {"id": str(numero), "type": "ValidateStep"})
        ET.SubElement(passo, "parameterizedString", {"isformatted": "true"}).text = (
            f"<p>{html.escape(acao)}</p>"
        )
        ET.SubElement(passo, "parameterizedString", {"isformatted": "true"}).text = (
            f"<p>{html.escape(esperado)}</p>"
        )
        ET.SubElement(passo, "description")
    xml = ET.tostring(raiz, encoding="unicode")
    ET.fromstring(xml)
    return xml


def listar_existentes(org, projeto):
    wiql = (
        "SELECT [System.Id], [System.Title] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "AND [System.WorkItemType] = 'Test Case' "
        "AND [System.Title] CONTAINS 'QA-S4-'"
    )
    dados = executar_az(
        "boards", "query", "--wiql", wiql, "--org", org, "--project", projeto
    )
    if dados is None:
        itens = []
    elif isinstance(dados, list):
        itens = dados
    elif isinstance(dados, dict):
        itens = dados.get("workItems", dados.get("value", []))
    else:
        raise ValueError("Resposta inesperada da consulta de casos existentes")
    existentes = {}
    for item in itens:
        campos = item.get("fields", {})
        titulo = campos.get("System.Title")
        if not titulo:
            detalhe = executar_az("boards", "work-item", "show", "--id", str(item["id"]), "--org", org)
            titulo = detalhe.get("fields", {}).get("System.Title")
        if titulo:
            existentes[titulo] = item["id"]
    return existentes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Criar ou atualizar no Azure Boards")
    parser.add_argument("--org", default="https://dev.azure.com/RM563197")
    parser.add_argument("--project", default="VetSync")
    args = parser.parse_args()

    casos = json.loads(ARQUIVO_CASOS.read_text(encoding="utf-8"))
    if len({caso["codigo"] for caso in casos}) != len(casos):
        parser.error("Codigos de caso duplicados")

    for caso in casos:
        passos_xml(caso)
        print(f'{caso["codigo"]}: {caso["titulo"]} ({len(caso["passos"])} passos)')

    if not args.apply:
        print("\nPrevia local. Nenhuma alteracao feita no Azure Boards.")
        return

    existentes = listar_existentes(args.org, args.project)
    for caso in casos:
        titulo = f'[{caso["codigo"]}] {caso["titulo"]}'
        campos = [
            "System.Tags=VetSync-QA-S4",
            "Microsoft.VSTS.TCM.Steps=" + passos_xml(caso),
        ]
        if titulo in existentes:
            item = executar_az(
                "boards", "work-item", "update", "--id", str(existentes[titulo]),
                "--description", descricao_html(caso), "--fields", *campos,
                "--org", args.org,
            )
            acao = "Atualizado"
        else:
            item = executar_az(
                "boards", "work-item", "create", "--type", "Test Case",
                "--title", titulo, "--description", descricao_html(caso),
                "--fields", *campos, "--org", args.org, "--project", args.project,
            )
            acao = "Criado"
        print(f'{acao}: {args.org}/{args.project}/_workitems/edit/{item["id"]}')


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)

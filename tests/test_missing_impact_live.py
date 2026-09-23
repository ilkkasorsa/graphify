"""Focused guards for the qualified live-only candidate universe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify import change_completeness as cc
from graphify import missing_impact as mi

TASK = " ".join(f"RocketEngine{index:02d}" for index in range(25))


def _fixture(tmp_path):
    root = tmp_path / "repo"
    nodes = [{"id": "seed", "label": "Seed", "source_file": "src/seed.py", "community": 0}]
    links = []
    for index in range(25):
        nodes.append({"id": f"local{index:02d}", "label": "Local", "source_file": f"src/local{index:02d}.py", "community": index + 1})
        links.append({"source": "seed", "target": f"local{index:02d}", "relation": "calls"})
        nodes.append({"id": f"anchor{index:02d}", "label": f"RocketEngine{index:02d}", "source_file": f"remote/anchor{index:02d}.py", "community": index + 100})
    graph = {"nodes": nodes, "links": links}
    for node in nodes:
        path = root / node["source_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture source must not be sent\n")
    graph_path = root / "graphify-out" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps(graph))
    return root, graph


def test_offline_order_and_budget_are_unchanged(tmp_path, monkeypatch):
    root, graph = _fixture(tmp_path)
    monkeypatch.setattr(mi, "call_typesafe", lambda *_: pytest.fail("offline network call"))
    projection = mi.project_graph(graph)
    expected = mi.candidates(projection, ["src/seed.py"], 12)
    analysis = mi.prepare_analysis(objective="RocketEngine", repo=root, changed_paths=["src/seed.py"])
    assert analysis["rows"] == expected
    assert [row["path"] for row in analysis["result"]["candidates"]] == [row["path"] for row in expected]
    assert analysis["result"]["candidate_budget"] == 12
    assert all("origin" not in row for row in analysis["result"]["candidates"])
    assert len(cc.build_plan(analysis)["candidates"]) == 12


def test_live_top20_union_provenance_and_payload(tmp_path):
    root, graph = _fixture(tmp_path)
    projection = mi.project_graph(graph)
    fingerprint = projection["fingerprint"]
    rows = mi.live_candidates(graph, projection, TASK, ["src/seed.py"], ["src/seed.py"], root)
    assert len(rows) == 40
    assert len({row["path"] for row in rows}) == 40
    assert [row["path"] for row in rows[:20]] == [row["path"] for row in mi.candidates(projection, ["src/seed.py"], 20)]
    assert [row["path"] for row in rows[20:]] == [f"remote/anchor{index:02d}.py" for index in range(20)]
    assert "src/seed.py" not in {row["path"] for row in rows}
    assert projection["fingerprint"] == fingerprint
    anchor = rows[20]
    assert anchor["origin"] == "CONCEPT_ANCHOR"
    assert "distance" not in anchor and "structural_rank" not in anchor
    assert anchor["matched_task_tokens"] == ["engine00"]
    payload = mi.jev_payload(TASK, projection, ["src/seed.py"], rows)
    assert payload["state"]["changed_seed_files"] == ["src/seed.py"]
    assert payload["state"]["candidates"][20]["origin"] == "concept_anchor"
    assert "local_structural_evidence" not in payload["state"]["candidates"][20]
    encoded = json.dumps(payload)
    for forbidden in ("fixture source", "baseline_score", "structural_rank", "concept_anchor_rank", "anchor_score", "hidden_target", "expected_relevance"):
        assert forbidden not in encoded
    assert all(row["path"] in payload["questions"][f"candidate_{index:02d}"]["instructions"] for index, row in enumerate(rows))


def test_concept_tokens_and_high_frequency_suppression():
    assert mi._concept_tokens("camelCase PascalCase snake_case kebab-case") == {"camel", "case", "pascal", "snake", "kebab"}
    graph = {"nodes": [{"id": str(index), "source_file": f"f{index}.py", "label": "GenericThing" if index < 5 else "UniqueThing"} for index in range(8)], "links": []}
    assert mi.concept_anchors(graph, "GenericThing", set()) == []
    assert mi.concept_anchors(graph, "UniqueThing", set()) == []
    graph["nodes"][7]["label"] = "RareCamelToken"
    assert [row["path"] for row in mi.concept_anchors(graph, "rareCamelToken", set())] == ["f7.py"]


def test_multi_channel_keeps_both_evidence_families_and_reads_no_source(tmp_path, monkeypatch):
    root, graph = _fixture(tmp_path)
    graph["nodes"][1]["label"] = "RareLocalConcept"
    projection = mi.project_graph(graph)
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: pytest.fail("source read"))
    rows = mi.live_candidates(graph, projection, "RareLocalConcept", ["src/seed.py"], ["src/seed.py"], root)
    row = next(row for row in rows if row["path"] == "src/local00.py")
    assert row["origin"] == "MULTI_CHANNEL"
    assert row["distance"] == 1
    assert row["matched_task_tokens"] == ["concept", "rare"]
    evidence = mi.jev_payload("RareLocalConcept", projection, ["src/seed.py"], rows)["state"]["candidates"][0]
    assert evidence["origin"] == "both"
    assert evidence["local_structural_evidence"]["distance"] == 1
    assert evidence["concept_evidence"]["matched_graph_labels"] == ["RareLocalConcept"]


def test_live_one_request_tie_break_top12_and_change_completeness(tmp_path, monkeypatch):
    root, _ = _fixture(tmp_path)
    calls = []
    def fake(payload, _key):
        calls.append(payload)
        return {"model": "jev-test", "usage": {}, "answers": {key: {"noul": 0.9 if row["origin"] == "concept_anchor" else 0.1}
            for key, row in zip(payload["questions"], payload["state"]["candidates"])}}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(mi, "call_typesafe", fake)
    analysis = mi.prepare_analysis(objective=TASK, repo=root, changed_paths=["src/seed.py"], live=True)
    mi.rerank_live(analysis)
    result = analysis["result"]
    assert len(calls) == 1
    assert len(result["candidates"]) == 12
    assert [row["path"] for row in result["candidates"]] == [f"remote/anchor{index:02d}.py" for index in range(12)]
    assert all(row["provenance"] == "JEV_INFERRED" and "distance" not in row for row in result["candidates"])
    plan = cc.build_plan(analysis)
    assert plan["status"] == "NEEDS_SOURCE_VERIFICATION"
    assert len(plan["candidates"]) == 12
    assert max(len(item["verify_candidates"]) for item in plan["dimensions"].values()) <= 12
    assert "origin CONCEPT_ANCHOR, concept tokens" in cc._human(plan, 12)
    assert "origin: CONCEPT_ANCHOR" in mi._human(result)
    assert "distance" not in mi._human(result)


def test_change_completeness_live_json_exposes_only_final_twelve(tmp_path, monkeypatch, capsys):
    root, _ = _fixture(tmp_path)
    calls = []
    def fake(payload, _key):
        calls.append(payload)
        return {"model": "jev-test", "usage": {}, "answers": {key: {"noul": float(index)}
            for index, key in enumerate(payload["questions"])}}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(mi, "call_typesafe", fake)
    cc.run(["--task", TASK, "--repo", str(root), "--changed", "src/seed.py", "--live", "--json"])
    plan = json.loads(capsys.readouterr().out)
    assert len(calls) == 1 and len(calls[0]["state"]["candidates"]) == 40
    assert len(plan["candidates"]) == 12
    assert all(set(item["verify_candidates"]) <= {row["path"] for row in plan["candidates"]}
               for item in plan["dimensions"].values())


def test_missing_key_only_blocks_live_and_no_represented_seed_skips_call(tmp_path, monkeypatch):
    root, _ = _fixture(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    offline = mi.prepare_analysis(objective="RocketEngine", repo=root, changed_paths=["src/seed.py"])
    assert offline["rows"]
    live = mi.prepare_analysis(objective="RocketEngine", repo=root, changed_paths=["src/seed.py"], live=True)
    with pytest.raises(mi.MissingImpactError, match="TYPESAFE_API_KEY"):
        mi.rerank_live(live)
    monkeypatch.setattr(mi, "call_typesafe", lambda *_: pytest.fail("unexpected call"))
    absent = mi.prepare_analysis(objective="RocketEngine", repo=root, changed_paths=["absent.py"], live=True)
    mi.rerank_live(absent)
    assert absent["status"] == "NO_GRAPH_REPRESENTED_SEEDS"

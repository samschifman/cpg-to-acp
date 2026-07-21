"""Tests for the LangGraph care plan pipeline."""

import logging

from langgraph.checkpoint.memory import MemorySaver

from acp_writer.pipeline import build_pipeline


class TestPipelineStructure:
    def test_graph_compiles(self):
        graph = build_pipeline()
        compiled = graph.compile()
        assert compiled is not None

    def test_expected_nodes(self):
        graph = build_pipeline()
        node_names = set(graph.nodes.keys())
        expected = {
            "condition_scanner",
            "guideline_resolver",
            "dmn_executor",
            "recommendation_retriever",
            "plan_composer",
            "brief_reviewer",
            "fhir_bundle_generator",
            "terminology_validator",
            "fhir_syntax_validator",
            "fhir_semantic_reviewer",
            "fhir_server_writer",
        }
        assert expected == node_names

    def test_eleven_nodes(self):
        graph = build_pipeline()
        assert len(graph.nodes) == 11


class TestPipelineExecution:
    def test_stub_pipeline_runs(self, caplog):
        graph = build_pipeline()
        compiled = graph.compile()
        result = compiled.invoke({"ips_bundle": {"resourceType": "Bundle"}})

        assert result["delivery_status"] == "skipped"
        assert result["fhir_bundle"]["resourceType"] == "Bundle"
        assert result["fhir_bundle"]["type"] == "transaction"

    def test_all_stubs_execute(self, caplog):
        graph = build_pipeline()
        compiled = graph.compile()

        with caplog.at_level(logging.INFO):
            compiled.invoke({"ips_bundle": {}})

        logged = caplog.text
        for node in [
            "condition_scanner",
            "guideline_resolver",
            "dmn_executor",
            "recommendation_retriever",
            "plan_composer",
            "brief_reviewer",
            "fhir_bundle_generator",
            "terminology_validator",
            "fhir_syntax_validator",
            "fhir_semantic_reviewer",
            "fhir_server_writer",
        ]:
            assert node in logged, f"Node {node} did not execute"

    def test_memorysaver_checkpoint(self):
        graph = build_pipeline()
        checkpointer = MemorySaver()
        compiled = graph.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "test-run-001"}}
        result = compiled.invoke({"ips_bundle": {}}, config=config)
        assert result["delivery_status"] == "skipped"

        state = compiled.get_state(config)
        assert state.values["delivery_status"] == "skipped"
